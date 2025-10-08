"""
Generate a reproducible boilerplate summary for CAT12 BIDS processing runs.
Outputs both Markdown and HTML files with system, software, and run details.
"""
import os
import sys
import platform
import socket
    info = {}
    info['date'] = datetime.datetime.now().isoformat()
    info['system'] = get_system_info()
    spm_version, cat_version = get_spm_cat_version(args.spm_script)
    info['spm_version'] = spm_version
    info['cat_version'] = cat_version
    info['cli_args'] = args.cli_args
    info['config_path'] = args.config_path if args.config_path else "default config"
    info['config'] = load_config(args.config_path)
    info['env_vars'] = get_env_vars()
    info['input_dir'] = args.input_dir
    info['output_dir'] = args.output_dir
    info['subjects'] = args.subjects  # Already a string
    info['sessions'] = args.sessions if args.sessions else 'N/A'

    # Try to extract CAT12 log info
    log_path = os.path.join(args.output_dir, "cat12_stdout.log")
    log_summary = ""
    if os.path.exists(log_path):
        with open(log_path) as logf:
            lines = logf.readlines()
        # Extract block with SPM/CAT/MATLAB version and main processing steps
        block = []
        in_block = False
        for line in lines:
            if ("SPM12" in line or "CAT12" in line or "MATLAB" in line or "Statistical Parametric Mapping" in line):
                in_block = True
            if in_block:
                block.append(line.rstrip())
                # End block after main processing steps (first 'Done' or 'Bye for now')
                if "Done" in line or "Bye for now" in line:
                    break
        if block:
            log_summary = "\n".join(block)
        # Also extract timing lines and main steps
        timing_lines = [l.rstrip() for l in lines if ("s" in l and any(kw in l for kw in ["registration", "denoising", "correction", "segmentation", "preprocessing", "estimation", "thickness"]))]
        if timing_lines:
            log_summary += "\n\n---\nCAT12 Processing Steps & Timing:\n" + "\n".join(timing_lines)
    info['cat12_log_summary'] = log_summary

    def render_markdown_with_log(info):
        md = render_markdown(info)
        if info.get('cat12_log_summary'):
            md += f"\n---\n**CAT12 Log Summary:**\n\n```
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "hostname": socket.gethostname(),
        return md

    def render_html_with_log(info):
        html = render_html(info)
        if info.get('cat12_log_summary'):
            html += f"<hr><h2>CAT12 Log Summary</h2><pre>{info['cat12_log_summary']}</pre>"
        return html

    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    with open(os.path.join(args.output_dir, "boilerplate.md"), "w") as f:
        f.write(render_markdown_with_log(info))
    with open(os.path.join(args.output_dir, "boilerplate.html"), "w") as f:
        f.write(render_html_with_log(info))
    print(f"Boilerplate written to {args.output_dir}/boilerplate.md and .html")
        "cpu": platform.processor(),
        "ram_gb": round(os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / (1024.**3), 2)
    }

def get_env_vars():
    keys = ["LD_LIBRARY_PATH", "SPM12_PATH", "CAT12_PATH", "SPMROOT"]
    env_dict = {k: os.environ.get(k, "not set") for k in keys}
    return '\n'.join([f"{k}={v}" for k, v in env_dict.items()])

def load_config(config_path):
    if not config_path or not os.path.exists(config_path):
        return {}
    if config_path.endswith(".json"):
        with open(config_path) as f:
            return json.load(f)
    elif config_path.endswith(".yaml") or config_path.endswith(".yml"):
        with open(config_path) as f:
            return yaml.safe_load(f)
    return {}

def render_markdown(info):
    md = f"""# CAT12 BIDS Processing Boilerplate

**Date:** {info['date']}
**Host:** {info['system']['hostname']}
**OS:** {info['system']['os']}
**Python:** {info['system']['python']}
**CPU:** {info['system']['cpu']}
**RAM:** {info['system']['ram_gb']} GB

---

**SPM12 Version:** {info['spm_version']}
**CAT12 Version:** {info['cat_version']}

---

**CLI Arguments:**
```
{info['cli_args']}
```

**Config File:** `{info['config_path']}`
```json
{json.dumps(info['config'], indent=2)}
```

**Environment Variables:**
```
{info['env_vars']}
```

**Input Directory:** `{info['input_dir']}`
**Output Directory:** `{info['output_dir']}`
**Subjects:** {info['subjects']}
**Sessions:** {info['sessions']}

---

*This boilerplate was auto-generated for reproducibility.*
"""
    return md

def render_html(info):
    html = f"""
<html><head><title>CAT12 BIDS Processing Boilerplate</title></head><body>
<h1>CAT12 BIDS Processing Boilerplate</h1>
<ul>
<li><b>Date:</b> {info['date']}</li>
<li><b>Host:</b> {info['system']['hostname']}</li>
<li><b>OS:</b> {info['system']['os']}</li>
<li><b>Python:</b> {info['system']['python']}</li>
<li><b>CPU:</b> {info['system']['cpu']}</li>
<li><b>RAM:</b> {info['system']['ram_gb']} GB</li>
</ul>
<hr>
<ul>
<li><b>SPM12 Version:</b> {info['spm_version']}</li>
<li><b>CAT12 Version:</b> {info['cat_version']}</li>
</ul>
<hr>
<b>CLI Arguments:</b><pre>{info['cli_args']}</pre>
<b>Config File:</b> {info['config_path']}<pre>{json.dumps(info['config'], indent=2)}</pre>
<b>Environment Variables:</b><pre>{info['env_vars']}</pre>
<b>Input Directory:</b> {info['input_dir']}<br>
<b>Output Directory:</b> {info['output_dir']}<br>
<b>Subjects:</b> {info['subjects']}<br>
<b>Sessions:</b> {info['sessions']}<br>
<hr>
<i>This boilerplate was auto-generated for reproducibility.</i>
</body></html>
"""
    return html

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate CAT12 BIDS boilerplate summary.")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--subjects", required=True, help="Comma-separated list of subject IDs")
    parser.add_argument("--sessions", default="", help="Comma-separated list of session IDs")
    parser.add_argument("--cli-args", required=True)
    parser.add_argument("--config-path", default="")
    parser.add_argument("--spm-script", required=True)
    args = parser.parse_args()

    info = {}
    info['date'] = datetime.datetime.now().isoformat()
    info['system'] = get_system_info()
    spm_version, cat_version = get_spm_cat_version(args.spm_script)
    info['spm_version'] = spm_version
    info['cat_version'] = cat_version
    info['cli_args'] = args.cli_args
    info['config_path'] = args.config_path if args.config_path else "default config"
    info['config'] = load_config(args.config_path)
    info['env_vars'] = get_env_vars()
    info['input_dir'] = args.input_dir
    info['output_dir'] = args.output_dir
    info['subjects'] = args.subjects  # Already a string
    info['sessions'] = args.sessions if args.sessions else 'N/A'

    md = render_markdown(info)
    html = render_html(info)
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    with open(os.path.join(args.output_dir, "boilerplate.md"), "w") as f:
        f.write(md)
    with open(os.path.join(args.output_dir, "boilerplate.html"), "w") as f:
        f.write(html)
    print(f"Boilerplate written to {args.output_dir}/boilerplate.md and .html")

if __name__ == "__main__":
    main()
