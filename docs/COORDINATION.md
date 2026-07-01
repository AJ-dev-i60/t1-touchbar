# Coordination — moved

This repo is now the **standalone kernel firmware driver** ("just make it work") and is
feature-complete. The cross-session coordination contract (it was shared while the driver and the
studio app lived in one monorepo) moved with the studio code to the **`t1-touchbar-studio`** repo
(`docs/COORDINATION.md` there), where active development continues.

The full historical contract — ownership boundaries, the `Device` API, the decisions log and its
archive — is preserved in that repo and in this repo's git history (before the split).
