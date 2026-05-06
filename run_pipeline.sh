#!/usr/bin/env bash
# Run all scripted phases on a target project.
# Phase 4 (subagent dispatch) requires Claude Code and is not scripted here.
#
# Usage:
#   ./run_pipeline.sh <project_root>                  # default: writes to <project>/.cartographer/
#   ./run_pipeline.sh <project_root> --readonly       # writes to ~/.cartographer/<hash>/
#   ./run_pipeline.sh <project_root> /custom/output   # writes to /custom/output/
#   CARTOGRAPHER_READONLY=1 ./run_pipeline.sh <root>  # env-var equivalent of --readonly

set -euo pipefail

PROJECT_ROOT="${1:?usage: ./run_pipeline.sh <project_root> [--readonly|<output_dir>]}"
shift || true

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)/scripts"

if [[ "${1:-}" == "--readonly" ]]; then
    OUTPUT_DIR="$(python "$SCRIPT_DIR/resolve_output_dir.py" "$PROJECT_ROOT" --readonly)"
    echo "▸ Readonly mode — output: $OUTPUT_DIR"
elif [[ -n "${1:-}" ]]; then
    OUTPUT_DIR="$(python "$SCRIPT_DIR/resolve_output_dir.py" "$PROJECT_ROOT" --explicit-output "$1")"
elif [[ -n "${CARTOGRAPHER_READONLY:-}" ]]; then
    OUTPUT_DIR="$(python "$SCRIPT_DIR/resolve_output_dir.py" "$PROJECT_ROOT" --readonly)"
    echo "▸ Readonly mode (env) — output: $OUTPUT_DIR"
else
    OUTPUT_DIR="$(python "$SCRIPT_DIR/resolve_output_dir.py" "$PROJECT_ROOT")"
fi

echo "▸ Phase 1: mapping project..."
python "$SCRIPT_DIR/map_project.py" "$PROJECT_ROOT" --output "$OUTPUT_DIR"

echo
echo "▸ Phase 1.5: tracing pipelines..."
python "$SCRIPT_DIR/trace_pipelines.py" \
    "$OUTPUT_DIR/project-map.json" \
    --output-dir "$OUTPUT_DIR"

echo
echo "▸ Phase 1.6: extracting OpenAPI + tracing endpoints..."
LIVE_URL_FLAG=""
if [[ -n "${CARTOGRAPHER_LIVE_URL:-}" ]]; then
    LIVE_URL_FLAG="--live-url $CARTOGRAPHER_LIVE_URL"
fi
python "$SCRIPT_DIR/extract_openapi.py" \
    "$OUTPUT_DIR/project-map.json" \
    --output-dir "$OUTPUT_DIR" \
    $LIVE_URL_FLAG
python "$SCRIPT_DIR/trace_endpoints.py" \
    "$OUTPUT_DIR/project-map.json" \
    --output-dir "$OUTPUT_DIR"

echo
echo "▸ Phase 2: classifying segments..."
python "$SCRIPT_DIR/classify_segments.py" \
    "$OUTPUT_DIR/project-map.json" \
    --output "$OUTPUT_DIR/segments.json"

echo
echo "▸ Phase 3: planning waves..."
python "$SCRIPT_DIR/plan_waves.py" \
    "$OUTPUT_DIR/segments.json" \
    --map "$OUTPUT_DIR/project-map.json" \
    --output "$OUTPUT_DIR/wave_plan.json"

echo
echo "▸ Phase 3.5: matching specialist agents..."
AGENTS_DIR="$(cd "$(dirname "$0")" && pwd)/agents"
python "$SCRIPT_DIR/match_specialists.py" \
    "$OUTPUT_DIR/wave_plan.json" \
    --segments "$OUTPUT_DIR/segments.json" \
    --agents-dir "$AGENTS_DIR"

echo
echo "▸ Phase 4: dispatch review subagents — RUN THIS IN CLAUDE CODE."
echo "  See SKILL.md → 'Phase 4 — Dispatch review subagents'"
echo "  Reports must be written to: $OUTPUT_DIR/reports/<segment>.md"
echo

if [[ -d "$OUTPUT_DIR/reports" ]]; then
    echo "▸ Phase 5: synthesizing findings..."
    python "$SCRIPT_DIR/synthesize.py" \
        "$OUTPUT_DIR/reports/" \
        --map "$OUTPUT_DIR/project-map.json" \
        --output "$OUTPUT_DIR/synthesis.json"
    echo
    echo "Done. See $OUTPUT_DIR/synthesis.md"
else
    echo "Skipping Phase 5 — no reports directory yet."
    echo "Once Claude Code has written per-segment reports, run:"
    echo "  python $SCRIPT_DIR/synthesize.py $OUTPUT_DIR/reports/ \\"
    echo "      --map $OUTPUT_DIR/project-map.json \\"
    echo "      --output $OUTPUT_DIR/synthesis.json"
fi

if [[ -f "$OUTPUT_DIR/backlog.md" ]]; then
    echo
    echo "▸ Phase 7 ready: backlog.md found."
    echo "  Build dispatch plan with:"
    echo "    python $SCRIPT_DIR/apply_backlog.py $OUTPUT_DIR/backlog.md \\"
    echo "        --output $OUTPUT_DIR/fix_plan.json"
    echo "  Then dispatch fix subagents in Claude Code per prompts/fix_agent.md"
fi
