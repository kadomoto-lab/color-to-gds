# Contributing to Color2GDS

Thanks for your interest! Issues and pull requests are welcome in English or Japanese.
（日本語でのIssue・プルリクエストも歓迎します。）

## Reporting bugs and asking questions

Please open an issue that includes the following.

- what you ran (CLI command, or the GUI settings) and the stack file you used
- what you expected and what happened, with the error message or log
- your OS and Python version

If a result looks physically wrong, attaching `manifest.json` and `summary.json` from the output folder helps a lot.

## Development setup

Dependencies are managed with [uv](https://docs.astral.sh/uv/).

```bash
uv sync
OPENBLAS_NUM_THREADS=1 uv run pytest -q
```

To add or upgrade a dependency, use `uv add <package>` (or `uv add --dev <package>` for test tools) and commit both `pyproject.toml` and `uv.lock`.

## Pull requests

- Keep each pull request focused on one change and describe why it is needed.
- Add or update tests in `test_*.py` when you change behavior.
- Make sure `pytest` passes before you submit.
- Follow the style of the surrounding code.
- Do not commit generated outputs (`runs/web/`, `.cache/`) or large binaries unless they are intentional sample data.

### Adding a layer stack

New presets go in `presets/` as YAML. Please cite where every thickness and material value comes from, and mark values that are assumptions. Material data added to `data/` must come with its source and a license that allows redistribution.

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
