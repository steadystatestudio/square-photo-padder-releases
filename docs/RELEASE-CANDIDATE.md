# Releasing Square Photo Padder 1.2.0

The public `square-photo-padder-releases` repository contains the current source.
The older private repository is preserved; do not reset or mirror its history.

After the reviewed source is merged to main, manually dispatch **Stage reviewed
release candidate (draft only)** with the exact 40-character main commit and
`v1.2.0`. A different workflow commit, non-main branch, automatic push, unexpected
repository, moved tag or published release is rejected. The complete paginated
release inventory is checked before draft creation. Staging never publishes or
changes repository visibility.

The workflow tests/builds on Windows Server 2022 and Ubuntu 22.04, checks the real
packaged GUI and JPEG outputs, then verifies and runs those exact retained Linux
package bytes on Ubuntu 24.04. Native library notices, matching dependency sources,
checksums, synthetic screenshots and test results accompany the draft.

Before publishing the final stable release, inspect `RELEASE-READY.json`, exact
asset digests, source/version agreement and the candidate screenshots. Exercise
the ordinary import, rotation, single-save, batch-save and cancellation paths on
the candidate. Test copies of synthetic photos, with originals preserved. An
unsigned package is not a signed distribution: keep that fact visible in the
download instructions. No beta flag should be changed merely to conceal missing
verification. Publish the tested bytes and retain their source commit unchanged.

Use the Windows ZIP, Linux AppImage and Linux tar.gz as the prominent downloads.
The large Qt/PySide source archives are required accompanying sources, not the app.
