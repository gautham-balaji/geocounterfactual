"""Build the Colab LoRA fine-tuning notebook."""
import json
import pathlib

def md(src):
    return {"cell_type": "markdown", "metadata": {},
            "source": src.strip("\n").splitlines(keepends=True)}

def code(src):
    return {"cell_type": "code", "execution_count": None, "metadata": {},
            "outputs": [], "source": src.strip("\n").splitlines(keepends=True)}

cells = []

cells.append(md("""
# GeoCounterfactual — SD 1.5 Inpainting LoRA

Fine-tunes the **same model the backend infers with**
(`stable-diffusion-v1-5/stable-diffusion-inpainting`) on ~1,500 before/after
Sentinel-2 patches of water-harvesting structures.

**Why LoRA on the inpainting UNet, not text-to-image.** The production
pipeline is `StableDiffusionControlNetInpaintPipeline`: the Planner emits a
change mask and the Generator fills it. Training the same objective means
the fine-tune matches inference exactly. The inpainting UNet takes 9 input
channels (4 noisy latent + 1 mask + 4 masked-image latent), and LoRA adapts
the attention projections, whose shapes are identical in both UNets.

**Why checkpointing is the hard part.** Free Colab reclaims a runtime after
~90 min idle and ~12 h maximum, without warning. Everything that matters
lives on Drive, checkpoints are written atomically, and a resume restores
optimizer and scheduler state — not just weights. Restoring weights alone
silently restarts the LR schedule, which quietly degrades the run.

**Runtime → Change runtime type → T4 GPU** before running anything.
"""))

cells.append(md("## 1. Runtime check and Drive"))

cells.append(code("""
import subprocess, sys
print(subprocess.run(['nvidia-smi','--query-gpu=name,memory.total',
                      '--format=csv,noheader'],
                     capture_output=True, text=True).stdout.strip() or
      'NO GPU — set Runtime > Change runtime type > T4 GPU and restart')

from google.colab import drive
drive.mount('/content/drive')
"""))

cells.append(code("""
import os, pathlib

ROOT = pathlib.Path('/content/drive/MyDrive/geocf')
DATASET_TAR = ROOT / 'pairs.tar'          # upload this once
DATASET_DIR = pathlib.Path('/content/pairs')   # extracted to LOCAL disk
CKPT_DIR    = ROOT / 'checkpoints'
STATE_FILE  = ROOT / 'state.json'
SAMPLE_DIR  = ROOT / 'samples'

for d in (ROOT, CKPT_DIR, SAMPLE_DIR):
    d.mkdir(parents=True, exist_ok=True)

print('drive root :', ROOT, '(exists:', ROOT.exists(), ')')
print('dataset tar:', DATASET_TAR, '(exists:', DATASET_TAR.exists(), ')')
"""))

cells.append(md("""
## 2. Dependencies

Pinned. `peft` supplies LoRA; `diffusers` 0.40 matches the backend so the
adapter loads there without a version dance.
"""))

cells.append(code("""
!pip install -q diffusers==0.40.0 transformers==4.44.2 accelerate==0.33.0 \\
                peft==0.12.0 safetensors==0.4.5 bitsandbytes==0.43.3
import torch, diffusers, peft
print('torch', torch.__version__, '| cuda', torch.cuda.is_available())
print('diffusers', diffusers.__version__, '| peft', peft.__version__)
"""))

cells.append(md("""
## 3. Dataset

Extract the tar to **local** disk, not Drive. Reading 3,000 small PNGs per
epoch over the Drive FUSE mount is roughly an order of magnitude slower
than local SSD and is the single biggest avoidable time sink in a Colab
training run.

Upload once from your machine:

```bash
cd backend/data
tar -cf pairs.tar pairs/
# then drag pairs.tar into Drive at MyDrive/geocf/
```
"""))

cells.append(code("""
import tarfile, time

if not DATASET_DIR.exists() or not any(DATASET_DIR.rglob('meta.json')):
    assert DATASET_TAR.exists(), f'Upload the dataset tar to {DATASET_TAR}'
    DATASET_DIR.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with tarfile.open(DATASET_TAR) as tf:
        tf.extractall('/content')
    # tar may contain a top-level 'pairs/' dir
    if not any(DATASET_DIR.rglob('meta.json')):
        for c in pathlib.Path('/content').iterdir():
            if c.is_dir() and any(c.rglob('meta.json')):
                DATASET_DIR = c
                break
    print(f'extracted in {time.time()-t0:.0f}s')

n = len(list(DATASET_DIR.glob('*/meta.json')))
print('pairs on local disk:', n, 'at', DATASET_DIR)
assert n > 0, 'No pairs found'
"""))

cells.append(md("""
### Dataset class

Two details worth stating:

**The mask is approximate.** Each patch is centred on the detected
structure by construction and we know its area and circularity, so the mask
is a centred ellipse of the right area and eccentricity. It is not the
exact footprint — that would need the SWIR band, and the extraction wrote
RGB only. It is close enough to teach "fill this region with a plausible
impoundment", which is what inference asks for.

**We train on the AFTER frame.** BEFORE is used for validation samples and
for the critic's evaluation set, not as a training input: this is an
inpainting objective, not image-to-image translation.
"""))

cells.append(code("""
import json, math, random
import numpy as np
import torch
from PIL import Image
from torch.utils.data import Dataset, DataLoader

RES = 512

class PairDataset(Dataset):
    def __init__(self, root, resolution=RES, seed=0):
        self.dirs = sorted(p.parent for p in pathlib.Path(root).glob('*/meta.json'))
        self.res = resolution
        self.rng = random.Random(seed)

    def __len__(self):
        return len(self.dirs)

    def _mask(self, meta):
        \"\"\"Centred ellipse matching the structure's area and shape.\"\"\"
        span_m = meta.get('patch_span_m', 1280)
        area_m2 = float(meta['area_ha']) * 1e4
        circ = float(meta.get('circularity', 0.6)) or 0.6
        # aspect from circularity: rounder -> closer to a circle
        aspect = max(1.0, min(4.0, 1.0 / max(circ, 0.15)))
        r_eq_m = math.sqrt(area_m2 / math.pi)
        a_m, b_m = r_eq_m * math.sqrt(aspect), r_eq_m / math.sqrt(aspect)
        px_per_m = self.res / span_m
        a, b = max(3.0, a_m * px_per_m), max(3.0, b_m * px_per_m)

        yy, xx = np.mgrid[0:self.res, 0:self.res]
        cy = cx = self.res / 2.0
        theta = self.rng.uniform(0, math.pi)
        xr = (xx - cx) * math.cos(theta) + (yy - cy) * math.sin(theta)
        yr = -(xx - cx) * math.sin(theta) + (yy - cy) * math.cos(theta)
        ell = (xr / a) ** 2 + (yr / b) ** 2 <= 1.0
        # dilate slightly: the model should also learn the wetted fringe
        pad = np.zeros_like(ell)
        k = 2
        for dy in range(-k, k + 1):
            for dx in range(-k, k + 1):
                pad |= np.roll(np.roll(ell, dy, 0), dx, 1)
        return pad.astype(np.float32)

    def __getitem__(self, i):
        d = self.dirs[i]
        meta = json.loads((d / 'meta.json').read_text())
        img = Image.open(d / 'after.png').convert('RGB').resize(
            (self.res, self.res), Image.LANCZOS)
        arr = np.asarray(img, dtype=np.float32) / 127.5 - 1.0   # [-1, 1]
        pixel_values = torch.from_numpy(arr).permute(2, 0, 1)

        mask = torch.from_numpy(self._mask(meta))[None]          # 1,H,W

        # Light augmentation. Flips only: rotation would resample and these
        # patches are already 4x upsampled.
        if self.rng.random() < 0.5:
            pixel_values = torch.flip(pixel_values, [2]); mask = torch.flip(mask, [2])
        if self.rng.random() < 0.5:
            pixel_values = torch.flip(pixel_values, [1]); mask = torch.flip(mask, [1])

        return {'pixel_values': pixel_values,
                'mask': mask,
                'caption': meta.get('caption', 'satellite view of a water harvesting structure'),
                'id': d.name}

ds = PairDataset(DATASET_DIR)
print('dataset size:', len(ds))
s = ds[0]
print('pixel_values', tuple(s['pixel_values'].shape), s['pixel_values'].min().item(),
      s['pixel_values'].max().item())
print('mask coverage: %.1f%%' % (100 * s['mask'].mean().item()))
print('caption:', s['caption'])
"""))

cells.append(md("## 4. Model and LoRA"))

cells.append(code("""
import torch
from diffusers import StableDiffusionInpaintPipeline, DDPMScheduler
from peft import LoraConfig, get_peft_model_state_dict, set_peft_model_state_dict

MODEL_ID = 'stable-diffusion-v1-5/stable-diffusion-inpainting'
device = 'cuda'
weight_dtype = torch.float16

pipe = StableDiffusionInpaintPipeline.from_pretrained(
    MODEL_ID, torch_dtype=weight_dtype, variant='fp16',
    use_safetensors=True, safety_checker=None, requires_safety_checker=False)

vae, unet = pipe.vae, pipe.unet
text_encoder, tokenizer = pipe.text_encoder, pipe.tokenizer
noise_scheduler = DDPMScheduler.from_pretrained(MODEL_ID, subfolder='scheduler')

vae.requires_grad_(False); text_encoder.requires_grad_(False)
unet.requires_grad_(False)
vae.to(device, dtype=weight_dtype)
text_encoder.to(device, dtype=weight_dtype)
unet.to(device, dtype=weight_dtype)

LORA_RANK = 16
lora_cfg = LoraConfig(
    r=LORA_RANK, lora_alpha=LORA_RANK, init_lora_weights='gaussian',
    # Attention projections only. Same shapes in the inpainting and t2i
    # UNets, so the adapter is portable between them.
    target_modules=['to_q', 'to_k', 'to_v', 'to_out.0'],
)
unet.add_adapter(lora_cfg)

# LoRA params must be fp32 even with an fp16 base, or the updates underflow.
for p in unet.parameters():
    if p.requires_grad:
        p.data = p.data.float()

trainable = [p for p in unet.parameters() if p.requires_grad]
print(f'trainable: {sum(p.numel() for p in trainable)/1e6:.2f} M '
      f'of {sum(p.numel() for p in unet.parameters())/1e6:.0f} M')

unet.enable_gradient_checkpointing()
pipe.set_progress_bar_config(disable=True)
"""))

cells.append(md("""
## 5. Checkpointing

The part that has to be right.

* **Atomic writes.** Save to a temp directory, then `os.replace`. A
  disconnect mid-write otherwise leaves a corrupt `latest/` and the run
  restarts from zero.
* **Optimizer and scheduler are saved too.** Weights alone restart the LR
  schedule at step 0, which is a silent quality regression rather than a
  visible failure.
* **Dataloader seed is derived from `global_step`,** so resuming does not
  replay the same sample order every session.
"""))

cells.append(code("""
import os, shutil, json, signal
import torch
from safetensors.torch import save_file, load_file

def save_checkpoint(unet, optimizer, lr_scheduler, global_step, epoch,
                    tag='latest'):
    target = CKPT_DIR / tag
    tmp = CKPT_DIR / f'.tmp_{tag}'
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)

    lora_sd = get_peft_model_state_dict(unet)
    save_file({k: v.detach().cpu().contiguous().to(torch.float32)
               for k, v in lora_sd.items()}, tmp / 'lora.safetensors')
    torch.save({'optimizer': optimizer.state_dict(),
                'lr_scheduler': lr_scheduler.state_dict()},
               tmp / 'optim.pt')
    (tmp / 'meta.json').write_text(json.dumps(
        {'global_step': global_step, 'epoch': epoch,
         'lora_rank': LORA_RANK, 'model_id': MODEL_ID}, indent=2))

    # Atomic swap.
    backup = CKPT_DIR / f'.old_{tag}'
    if target.exists():
        if backup.exists():
            shutil.rmtree(backup)
        os.replace(target, backup)
    os.replace(tmp, target)
    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True)

    STATE_FILE.write_text(json.dumps(
        {'global_step': global_step, 'epoch': epoch,
         'updated': time.strftime('%Y-%m-%d %H:%M:%S')}, indent=2))
    return target


def load_checkpoint(unet, optimizer=None, lr_scheduler=None, tag='latest'):
    src = CKPT_DIR / tag
    if not (src / 'lora.safetensors').is_file():
        print('no checkpoint; starting fresh')
        return 0, 0
    meta = json.loads((src / 'meta.json').read_text())
    if meta.get('lora_rank') != LORA_RANK:
        raise RuntimeError(f"checkpoint rank {meta.get('lora_rank')} != {LORA_RANK}")

    sd = load_file(src / 'lora.safetensors')
    set_peft_model_state_dict(unet, sd)
    if optimizer is not None and (src / 'optim.pt').is_file():
        blob = torch.load(src / 'optim.pt', map_location='cpu')
        optimizer.load_state_dict(blob['optimizer'])
        if lr_scheduler is not None:
            lr_scheduler.load_state_dict(blob['lr_scheduler'])
    print(f"resumed at step {meta['global_step']} (epoch {meta['epoch']})")
    return meta['global_step'], meta['epoch']
"""))

cells.append(md("## 6. Training configuration"))

cells.append(code("""
from torch.optim import AdamW
from diffusers.optimization import get_scheduler

EPOCHS            = 6
BATCH_SIZE        = 1      # T4 at 512 with the 9-channel inpainting UNet
GRAD_ACCUM        = 4      # effective batch 4
LEARNING_RATE     = 1e-4   # typical for LoRA; 10-100x a full fine-tune
LR_WARMUP         = 100
MAX_GRAD_NORM     = 1.0
MASK_LOSS_WEIGHT  = 9.0    # masked latents count 10x context
CHECKPOINT_EVERY  = 250    # ~10 MB each, so this costs seconds
SAMPLE_EVERY      = 500
SNAPSHOT_EVERY    = 1000   # keep a permanent step_XXXXXX copy

steps_per_epoch = max(1, len(ds) // (BATCH_SIZE * GRAD_ACCUM))
MAX_STEPS = steps_per_epoch * EPOCHS

optimizer = AdamW(trainable, lr=LEARNING_RATE, betas=(0.9, 0.999),
                  weight_decay=1e-2, eps=1e-8)
lr_scheduler = get_scheduler('cosine', optimizer=optimizer,
                             num_warmup_steps=LR_WARMUP,
                             num_training_steps=MAX_STEPS)

print(f'{len(ds)} pairs | {steps_per_epoch} steps/epoch | {MAX_STEPS} total')
print(f'~{MAX_STEPS * 1.5 / 60:.0f} min at 1.5 s/step on a T4')
"""))

cells.append(md("""
## 7. Training loop

The loop implements the inpainting objective directly: the UNet receives
`[noisy_latents, mask, masked_image_latents]` concatenated to 9 channels and
predicts the noise, exactly as the pipeline does at inference.

A SIGTERM/SIGINT handler saves before the runtime dies, so an interrupt
costs at most one step rather than up to 250.
"""))

cells.append(code("""
import torch.nn.functional as F
from tqdm.auto import tqdm

_interrupted = {'flag': False}
def _handler(signum, frame):
    _interrupted['flag'] = True
    print('\\ninterrupt received — will checkpoint and stop after this step')
signal.signal(signal.SIGINT, _handler)
try:
    signal.signal(signal.SIGTERM, _handler)
except Exception:
    pass


def encode_prompts(captions):
    ids = tokenizer(list(captions), padding='max_length',
                    max_length=tokenizer.model_max_length, truncation=True,
                    return_tensors='pt').input_ids.to(device)
    with torch.no_grad():
        return text_encoder(ids)[0].to(dtype=weight_dtype)


def training_step(batch):
    px = batch['pixel_values'].to(device, dtype=weight_dtype)
    mask = batch['mask'].to(device, dtype=weight_dtype)

    with torch.no_grad():
        latents = vae.encode(px).latent_dist.sample() * vae.config.scaling_factor
        # Masked image: what the model can see. Its latent is one of the
        # nine input channels.
        masked_px = px * (mask < 0.5)
        masked_latents = vae.encode(masked_px).latent_dist.sample() \\
            * vae.config.scaling_factor

    noise = torch.randn_like(latents)
    bsz = latents.shape[0]
    timesteps = torch.randint(0, noise_scheduler.config.num_train_timesteps,
                              (bsz,), device=device).long()
    noisy = noise_scheduler.add_noise(latents, noise, timesteps)

    mask_latent = F.interpolate(mask, size=latents.shape[-2:], mode='nearest')
    model_input = torch.cat([noisy, mask_latent, masked_latents], dim=1)

    enc = encode_prompts(batch['caption'])
    pred = unet(model_input, timesteps, encoder_hidden_states=enc).sample

    target = (noise if noise_scheduler.config.prediction_type == 'epsilon'
              else noise_scheduler.get_velocity(latents, noise, timesteps))

    # Mask-weighted loss. A 1 ha structure in a 1280 m patch covers under 1%
    # of the latent area, so a plain full-latent MSE is dominated by context
    # the model can copy verbatim and it would barely learn the structure.
    # Upweighting the masked region concentrates the gradient where the
    # actual task is, while keeping some signal outside so the fill stays
    # consistent with its surroundings.
    w = 1.0 + MASK_LOSS_WEIGHT * mask_latent.float()
    se = (pred.float() - target.float()) ** 2
    return (se * w).mean() / w.mean()


global_step, start_epoch = load_checkpoint(unet, optimizer, lr_scheduler)

progress = tqdm(total=MAX_STEPS, initial=global_step, desc='training')
unet.train()
stop = False

for epoch in range(start_epoch, EPOCHS):
    if stop:
        break
    # Seed from global_step so a resume does not replay the same order.
    loader = DataLoader(PairDataset(DATASET_DIR, seed=global_step + epoch),
                        batch_size=BATCH_SIZE, shuffle=True, num_workers=2,
                        pin_memory=True, drop_last=True)
    accum, running = 0, 0.0

    for batch in loader:
        loss = training_step(batch) / GRAD_ACCUM
        loss.backward()
        running += loss.item()
        accum += 1

        if accum % GRAD_ACCUM:
            continue

        torch.nn.utils.clip_grad_norm_(trainable, MAX_GRAD_NORM)
        optimizer.step(); lr_scheduler.step(); optimizer.zero_grad(set_to_none=True)
        global_step += 1
        progress.update(1)
        progress.set_postfix(loss=f'{running:.4f}',
                             lr=f'{lr_scheduler.get_last_lr()[0]:.2e}')
        running = 0.0

        if global_step % CHECKPOINT_EVERY == 0:
            save_checkpoint(unet, optimizer, lr_scheduler, global_step, epoch)
        if global_step % SNAPSHOT_EVERY == 0:
            save_checkpoint(unet, optimizer, lr_scheduler, global_step, epoch,
                            tag=f'step_{global_step:06d}')
        if _interrupted['flag'] or global_step >= MAX_STEPS:
            stop = True
            break

save_checkpoint(unet, optimizer, lr_scheduler, global_step,
                min(epoch, EPOCHS - 1))
progress.close()
print('stopped at step', global_step,
      '(interrupted)' if _interrupted['flag'] else '(complete)')
print('Re-run this cell to resume — it picks up from the checkpoint.')
"""))

cells.append(md("""
## 8. Sample check

Generate into a held-out patch's mask and compare against the real after
frame. Eyeball whether the model paints a plausible impoundment rather than
a blue blob.
"""))

cells.append(code("""
from PIL import Image
import numpy as np, json

unet.eval()
pipe.unet = unet
pipe.to(device)

eval_ds = PairDataset(DATASET_DIR, seed=999)
idx = [0, len(eval_ds)//3, 2*len(eval_ds)//3]

for i in idx:
    s = eval_ds[i]
    d = eval_ds.dirs[i]
    before = Image.open(d/'before.png').convert('RGB').resize((RES, RES))
    after  = Image.open(d/'after.png').convert('RGB').resize((RES, RES))
    mask_img = Image.fromarray((s['mask'][0].numpy()*255).astype('uint8'))

    with torch.autocast('cuda'):
        gen = pipe(prompt=s['caption'], image=before, mask_image=mask_img,
                   num_inference_steps=30, guidance_scale=7.5,
                   generator=torch.Generator('cuda').manual_seed(0)).images[0]

    strip = Image.new('RGB', (RES*4, RES))
    for k, im in enumerate([before, mask_img.convert('RGB'), gen, after]):
        strip.paste(im, (k*RES, 0))
    out = SAMPLE_DIR / f'step{global_step:06d}_{s["id"]}.png'
    strip.save(out)
    print(s['id'], '->', out.name, '(before | mask | generated | real after)')

unet.train()
"""))

cells.append(md("""
## 9. Export for the backend

Copies the adapter to a stable path. Download
`geocf_lora.safetensors` and drop it into
`backend/generator/weights/` on the dev machine.
"""))

cells.append(code("""
import shutil
src = CKPT_DIR / 'latest' / 'lora.safetensors'
dst = ROOT / 'geocf_lora.safetensors'
shutil.copy2(src, dst)
meta = json.loads((CKPT_DIR/'latest'/'meta.json').read_text())
print('exported', dst)
print('  step', meta['global_step'], '| rank', meta['lora_rank'])
print('  size %.1f MB' % (dst.stat().st_size/1e6))
print('\\nBackend load:')
print("  pipe.load_lora_weights('backend/generator/weights/geocf_lora.safetensors')")
"""))

nb = {
    "cells": cells,
    "metadata": {
        "accelerator": "GPU",
        "colab": {"provenance": [], "gpuType": "T4"},
        "kernelspec": {"display_name": "Python 3", "name": "python3"},
        "language_info": {"name": "python"},
    },
    "nbformat": 4,
    "nbformat_minor": 0,
}

out = pathlib.Path("notebooks/geocf_lora_finetune.ipynb")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(nb, indent=1), encoding="utf-8")
print("wrote", out, f"({len(cells)} cells)")
