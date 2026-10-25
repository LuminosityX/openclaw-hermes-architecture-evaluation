# Native Windows CLI verification

This bundle was prepared on Linux. Native Windows execution is pending; the bundle does not establish a Windows pass or failure for either product.

## Requirements

- Windows 10 or 11 on x64 or ARM64, with PowerShell.
- At least 12 GiB of free space on the experiment drive before starting.
- Network access to the pinned Node.js, npm, GitHub, and Python package downloads.

No public IP address, remote login, or model API key is required.

## Run

Copy the complete bundle to Windows, open PowerShell in that directory, and run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Run-Windows.ps1"
```

The execution-policy override applies only to this new PowerShell process. It does not change persistent user or system policy.

By default, the script creates a new `och-xxxxxxxx` directory under the system temporary directory. Use `-ExperimentRoot` to choose a different directory that does not already exist. At completion, or after a handled setup error, the script reports the location of `windows-results.zip`.

## Coverage

The bundle creates three independent configuration and state profiles per pinned product. It uses native file tools to write content containing Chinese characters and emoji, closes the client, reads the result from another native process, and checks that the native database retains the earlier user record.

A deterministic protocol service binds only to loopback. The installed products execute the tools; paid model calls are zero. Coverage is limited to the native Windows CLI. It does not establish GUI, Gateway, background-service, or full Linux-to-Windows state-migration behavior.

Setup, network, and script errors require log review. They must not automatically become a weak product rating.

## Versions and storage

The pinned versions are OpenClaw `2026.10.6` (`fe06181`), Hermes `0.22.5` (`bf0203a`), and Node.js `24.22.1`. Download locations and hashes are recorded in [pins.json](pins.json).

The runner does not read existing agent configurations or credentials, persist user PATH changes, or register background services. Each product's dependencies are installed once and shared across its three cases. No new stage or case starts when free space drops below 6 GiB.

The result package contains small native state records, inputs, outputs, logs, and manifests. Installed dependencies and caches are excluded. After preserving the result package, remove only the dedicated experiment directory printed by the runner to reclaim its storage.
