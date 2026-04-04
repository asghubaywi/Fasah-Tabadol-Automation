//! fasah-engine CLI
//!
//! # Commands
//!
//! ```bash
//! # Parse a CSV file → JSON ParseResult to stdout
//! fasah-engine parse declarations.csv
//!
//! # Parse a JSON file → JSON ParseResult to stdout
//! fasah-engine parse declarations.json
//!
//! # Check compliance (uses built-in default rules)
//! fasah-engine check parse_result.json
//!
//! # Check compliance with custom rules file
//! fasah-engine check parse_result.json --rules config/fasah_rules.yaml
//!
//! # Scan browser results directory
//! fasah-engine watch workspace/outbox/browser_results workspace/outbox
//! ```

use anyhow::Context;
use fasah_engine::{
    compliance::{ComplianceChecker, ComplianceRules},
    dispatcher::BrowserDispatcher,
    parser::DeclarationParser,
    result_watcher::scan_results,
};
use std::path::PathBuf;

fn main() -> anyhow::Result<()> {
    let args: Vec<String> = std::env::args().collect();

    if args.len() < 3 {
        print_usage();
        std::process::exit(1);
    }

    let command = &args[1];
    let file_path = PathBuf::from(&args[2]);

    match command.as_str() {
        "parse" => cmd_parse(&file_path, &args),
        "check" => cmd_check(&file_path, &args),
        "watch" => {
            if args.len() < 4 {
                eprintln!("Usage: fasah-engine watch <results_dir> <outbox_dir> [--max-retries N]");
                std::process::exit(1);
            }
            let outbox_dir = PathBuf::from(&args[3]);
            cmd_watch(&file_path, &outbox_dir, &args)
        }
        other => {
            eprintln!("Unknown command '{}'. Expected: parse, check, watch", other);
            std::process::exit(1);
        }
    }
}

fn cmd_parse(file_path: &PathBuf, args: &[String]) -> anyhow::Result<()> {
    let content = std::fs::read_to_string(file_path)
        .with_context(|| format!("cannot read '{}'", file_path.display()))?;

    let is_json = args.contains(&"--json".to_string())
        || file_path.extension().map(|e| e == "json").unwrap_or(false);

    let result = if is_json {
        DeclarationParser::parse_json(&content)
    } else {
        DeclarationParser::parse_csv(&content)
    }
    .map_err(|e| anyhow::anyhow!("{}", e))?;

    println!("{}", serde_json::to_string_pretty(&result)?);
    Ok(())
}

fn cmd_check(file_path: &PathBuf, args: &[String]) -> anyhow::Result<()> {
    let content = std::fs::read_to_string(file_path)
        .with_context(|| format!("cannot read '{}'", file_path.display()))?;

    // Accept either a ParseResult JSON or a plain DeclarationRecord array
    let declarations = if let Ok(parse_result) =
        serde_json::from_str::<fasah_engine::parser::ParseResult>(&content)
    {
        parse_result.records
    } else {
        serde_json::from_str(&content)
            .context("expected ParseResult JSON or DeclarationRecord array")?
    };

    // Load rules from file or use defaults
    let rules = if let Some(pos) = args.iter().position(|a| a == "--rules") {
        let rules_path = args.get(pos + 1).context("--rules requires a path argument")?;
        let rules_content = std::fs::read_to_string(rules_path)
            .with_context(|| format!("cannot read rules file '{}'", rules_path))?;
        serde_yaml::from_str::<ComplianceRules>(&rules_content)
            .context("invalid rules YAML")?
    } else {
        ComplianceRules::default()
    };

    let result = ComplianceChecker::check_all(&declarations, &rules);
    println!("{}", serde_json::to_string_pretty(&result)?);
    Ok(())
}

fn cmd_watch(
    results_dir: &PathBuf,
    outbox_dir: &PathBuf,
    args: &[String],
) -> anyhow::Result<()> {
    let max_retries = args
        .iter()
        .position(|a| a == "--max-retries")
        .and_then(|i| args.get(i + 1))
        .and_then(|v| v.parse::<u32>().ok())
        .unwrap_or(3);

    let tasks_dir = results_dir
        .parent()
        .map(|p| p.join("browser_tasks"))
        .unwrap_or_else(|| PathBuf::from("browser_tasks"));

    let mut dispatcher = BrowserDispatcher::new(&tasks_dir)?;
    let actions = scan_results(results_dir, &mut dispatcher, outbox_dir, max_retries)?;
    println!("{}", serde_json::to_string_pretty(&actions)?);
    Ok(())
}

fn print_usage() {
    eprintln!("fasah-engine — Fasah/Tabadol Customs Clearance Engine");
    eprintln!();
    eprintln!("USAGE:");
    eprintln!("  fasah-engine parse <file.csv>                          # Parse CSV → JSON");
    eprintln!("  fasah-engine parse <file.json>                         # Parse JSON array → JSON");
    eprintln!("  fasah-engine check <declarations.json>                 # Check compliance (default rules)");
    eprintln!("  fasah-engine check <file.json> --rules <rules.yaml>   # Check with custom rules");
    eprintln!("  fasah-engine watch <results_dir> <outbox_dir>         # Process browser results");
    eprintln!("              [--max-retries N]                          # Default: 3");
    eprintln!();
    eprintln!("ENVIRONMENT:");
    eprintln!("  FASAH_BASE_URL   Fasah portal URL (default: https://fasah.gov.sa)");
    eprintln!("  RUST_LOG         Logging level (default: info)");
}
