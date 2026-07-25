## 2024-05-24 - CLI Output Alignment Bug
**Learning:** Fixed a visual alignment issue in the CLI `channels` command output where columns were misaligned if all channel names were shorter than the column header "CHANNEL".
**Action:** Always ensure dynamic column width calculation accounts for the length of the column headers, not just the data, to guarantee visual alignment.
