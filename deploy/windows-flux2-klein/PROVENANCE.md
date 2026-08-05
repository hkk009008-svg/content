# FLUX.2 Klein artifact provenance decision

This record separates static source/format evidence from installation and GPU
execution. Nothing described here promotes the candidate beyond
`not_installed`.

## VAE: official BFL artifact selected

The candidate uses the direct BF16 file
`vae/diffusion_pytorch_model.safetensors` from the pinned Black Forest Labs
FLUX.2 Klein 4B repository commit
`5e67da950fce4a097bc150c22958a05716994cea`:

- bytes: `168120878`
- SHA-256: `ca70d2202afe6415bdbcb8793ba8cd99fd159cfe6192381504d6c4d3036e0f04`
- license source: BFL repository declaration, Apache-2.0
- safetensors contents: 251 tensors; 250 BF16 and one I64

Offline comparison against the previously selected Comfy F32 VAE found the
same 251 tensor names and shapes. Rounding each F32 tensor to BF16 produced the
official BFL tensor bit-for-bit; the I64 tensor also matched. This proves the
static tensor correspondence used to replace the mirror artifact. It does not
prove a successful ComfyUI execution.

The pinned ComfyUI core `VAELoader` enumerates any file under `models/vae`,
loads safetensors on CPU, recognizes BF16, and constructs `comfy.sd.VAE` from
the state dictionary. The matching `decoder.conv_in.weight` and
`bn.running_mean` keys select the same FLUX.2-compatible architecture branch,
whose working dtypes include BF16. That is sufficient for this offline
candidate contract; a real fixed probe is still required after installation.

## Qwen: official shards selected, deterministic digest resolved

The Comfy mirror is no longer an installation source. The candidate instead
pins the two Qwen3ForCausalLM BF16 text-encoder shards and index from the same
official BFL Apache repository commit:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `model-00001-of-00002.safetensors` | 4,967,215,360 | `8c0506e7f4936fa7e26183a4fd8da4e2bdbc5990ba64ae441f965d51228f36ea` |
| `model-00002-of-00002.safetensors` | 3,077,766,632 | `82f2bd839378541b0557bfabaf37c7d3d637071fdcb73302dedd7cf61162ce07` |
| `model.safetensors.index.json` | 32,855 | `06b3d5319b6d76d1a4a2433419180016cfd54ed62d086a5e6567a809f8c82634` |

Header-only inspection established that the official shard union and the known
Comfy-compatible single file have the same 398 tensor names, dtypes, and
shapes. A lexicographic merge that omits `__metadata__`, matching the known
single-file structure, synthesizes the same 45,848-byte header and an expected
total size of 8,044,982,048 bytes. Header and size agreement do not prove
payload identity: the mirror file's `6c671498...` digest is not the digest of a
merge from these pinned official shards.

On 2026-08-06, two independent no-output streaming derivations verified the
three pinned source hashes, reconstructed all 398 indexed tensor spans with the
declared lexicographic/no-metadata serialization, and produced the same complete
SHA-256, `e37269b7ca1301ad72a92627ce95432ab5aad5f89143a06055886aad3419d12f`.
One pass used an independent reconstruction and the other used the production
helper's source/header selection. Neither pass changed the source shards or
published a model destination.

`merge_qwen_encoder.py` is therefore the mandatory source boundary. It:

1. verifies the official index and both complete shard hashes;
2. validates safetensors shapes, byte spans, index coverage, and uniqueness;
3. streams tensors in lexicographic name order into a new file;
4. refuses to overwrite an existing destination; and
5. publishes only if the complete derived file matches SHA-256
   `e37269b7ca1301ad72a92627ce95432ab5aad5f89143a06055886aad3419d12f`.

Until that complete merge succeeds, Qwen provenance is
`official_source_derivation_not_execution_proven`, license approval remains
conditional, and the capability cannot become `ready`.
