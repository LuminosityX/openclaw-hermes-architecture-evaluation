# Contributing

Keep changes focused on the V6 source archive. Use English for repository documentation, issue descriptions, and pull request descriptions. Preserve multilingual inputs and upstream quotations where they are part of the experiment.

Before submitting a change:

1. Run `python3 tools/check_repository.py` from the repository root.
2. Explain the problem, the changed behavior or documentation, and the validation performed.
3. Keep runtime installations, logs, databases, generated results, and credentials out of the commit.

Do not reformat vendored sources, rewrite frozen protocol fields, or translate task prompts as documentation cleanup. Behavioral changes require a separately identified experiment revision and evidence; V6 remains the historical reference.

If an intentional archive packaging change modifies a file under `v6/`, update its inventory with `python3 tools/update_manifest.py`, review the manifest diff, and run the checks again. This updates recorded hashes; it does not validate changed experiment behavior. Keep the source index and Windows bundle manifest consistent with any affected file.

Use the existing upstream licenses for third-party files. Changes to the licensing of the original evaluation materials require an explicit decision by their rights holders.
