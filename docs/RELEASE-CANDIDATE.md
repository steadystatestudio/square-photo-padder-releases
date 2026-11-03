# Release preparation

Square Photo Padder 1.2.3 follows the desktop UI font and text-size settings.
At narrow widths, controls wrap and the work area scrolls without shrinking text.
Reopen the app after changing desktop font settings. Inspect normal and enlarged
fonts in the exact Windows and Linux packages, including Linux Mint Cinnamon.
Check toolbar actions, settings, dialogs, persistent status and actual saved output.

Run **Build release** from `.github/workflows/build-release.yml` on `main`, with
the exact 40-character commit and `v1.2.3`. The workflow supports the canonical
`steadystatestudio/square-photo-padder-releases` source repository and the private
`steadystatestudio/square-photo-padder-builds` build repository. A different
commit, branch, repository, moved tag or published release is rejected. The
complete paginated release inventory is checked before creating a draft. A
new draft's list entry may take a short time to appear; the helper makes bounded
read-only retries while continuing to reject ambiguous or changed releases.

Logs for release builds stay in the private build repository. Public release files include
source identifiers, checksums, build metadata, automated test results and
synthetic QA. Those files describe the selected source and packages; they do
not certify every desktop, display, filesystem or accessibility setup.

The workflow tests and builds on Windows Server 2022 and Ubuntu 22.04. It checks
packaged GUI behavior and JPEG output, then verifies and runs those exact Linux
package bytes on Ubuntu 24.04. Matching dependency sources, library notices,
checksums, screenshots and test results accompany the release files.

Before publishing, inspect `RELEASE-READY.json`, asset digests, source/version
agreement and screenshots. Exercise import, rotation, Save Photo, Process All
and cancellation on the candidate packages using synthetic photo copies.
Check outputs independently and preserve originals. Packages are unsigned;
download instructions must continue to say so. Publish the tested bytes with
their matching source commit and tag.

Use the Windows ZIP, Linux AppImage and Linux tar.gz as the main downloads.
The Qt/PySide source archives are accompanying dependency sources, rather than
application installers.
