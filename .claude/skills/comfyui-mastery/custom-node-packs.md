# Pinned custom-node surface

The FLUX.2 Klein image candidate uses only pinned ComfyUI core classes. Do not
install a community pack to satisfy or modify that graph.

The LivePortrait performance worker has exactly two pinned nested custom-node
repositories:

| Repository | Purpose | Authority |
| --- | --- | --- |
| ComfyUI-LivePortraitKJ | LivePortrait model, crop, retarget, process, and composite nodes | `deploy/windows-liveportrait-worker/revisions.json` |
| ComfyUI-VideoHelperSuite | Bounded driving-video load and H.264 MP4 combine | `deploy/windows-liveportrait-worker/revisions.json` |

The installer checks origin, exact commit, tracked/untracked state, dependency
lock, and package inventory. A repository that imports successfully but has a
different commit or untracked source is not the shipping worker.

## Required LivePortrait classes

- `VHS_LoadVideo`
- `VHS_VideoCombine`
- `DownloadAndLoadLivePortraitModels`
- `LivePortraitLoadMediaPipeCropper`
- `LivePortraitCropper`
- `LivePortraitRetargeting`
- `LivePortraitProcess`
- `LivePortraitComposite`

The authoritative required set is derived by
`performance.live_portrait_workflow.required_live_portrait_node_classes()`.
Validate every input field against the authenticated live `/object_info`
response at the pinned worker revision.

## Change policy

- Do not use ComfyUI Manager to update the production checkout.
- Do not install an extra pack to work around a missing class.
- Do not patch code in place on Windows and keep using old readiness evidence.
- Update the tracked revision/dependency/package contracts, rebuild the worker,
  rerun its fixed execution proof and benchmark, and retain new immutable
  evidence for any intended change.
