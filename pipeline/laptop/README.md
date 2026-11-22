# Training on the RTX laptop

The Mac makes the training set; the Windows laptop with the NVIDIA card trains the splat with
LichtFeld Studio; the result comes back to the Mac. Nothing is installed remotely and nothing needs a
network share: a USB stick carries the files both ways.

## Once: check the laptop (10 minutes)

1. Open PowerShell and run
   `nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap --format=csv`.
   Write down the four values for STATUS: GPU name, memory (VRAM), driver version, compute capability.
2. The compute capability must be **7.5 or higher** (RTX 20 or GTX 16 series and later): LichtFeld's
   Windows builds carry no kernels for older cards. If it is lower, skip LichtFeld and train with
   Brush (below).
3. The driver must be **570 or newer**. If it is older, update it with the NVIDIA app and restart.
4. Get LichtFeld Studio. Its current Windows builds are no longer on GitHub Releases; there are three
   routes, and the choice (and any donation) is the project owner's:
   - **An older GPLv3 build** (free): a Windows nightly from before the portal, such as the one
     labelled 0.4.2 (3 Feb 2026). Unzip it (it may hold a second zip inside) and note the full path
     of `bin\LichtFeld-Studio.exe`. `train.ps1` reads its `--help` and stops if a flag it uses is
     missing.
   - **The LichtFeld Portal** (portal.lichtfeld.io): the current build, from USD 30.
   - **Build from source** (free, GPLv3): Visual Studio 2022 17.10 or newer with the Clang component,
     and CUDA 12.8 or newer, then follow the build steps in the LichtFeld Studio repository.
5. Record the LichtFeld version in STATUS.

## Each run

On the Mac, from `pipeline/`, once `colmap_report.py` has said PASS:

```bash
uv run python export_training_set.py                              # work/train
uv run python export_training_set.py --subset 20 --out work/train_dry
ls /Volumes                                                       # find the stick's name
STICK=/Volumes/NAME_OF_STICK
mkdir -p "$STICK/herebeink"
cp -R work/train work/train_dry laptop/train.ps1 "$STICK/herebeink/"
```

On the laptop:

1. Copy the `herebeink` folder from the stick to `C:\herebeink\` (training from the stick is slow).
2. Open PowerShell in `C:\herebeink\` and run, with the path from step 3 above:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\train.ps1 -Exe "C:\path\to\LichtFeld-Studio.exe"
   ```

   The script prints the GPU, checks the driver, checks that this LichtFeld build knows every flag it
   uses (it stops and says which one if not: the flags come from LichtFeld's wiki and are unconfirmed
   until this check passes), trains 500 iterations on 20 images to prove the loader reads the folder
   layout, then trains the full set: MCMC, 30,000 iterations, at most 1.5 million splats, spherical
   harmonics degree 3, images at 1440 px, with held-out evaluation.
3. Leave it running (one to three hours, depending on the card). Keep the laptop on mains power.
4. When it says **Done**, copy these four files from `C:\herebeink\out\` to the stick:
   `splat_raw.ply`, `gpu.txt`, `train-summary.txt`, `full-output.txt`.

Back on the Mac, put them in `pipeline/work/splat/` (that folder is not committed):

```bash
mkdir -p work/splat
cp "$STICK"/herebeink/out/{splat_raw.ply,gpu.txt,train-summary.txt,full-output.txt} work/splat/
```

Record the iterations, the minutes, the splat count and the PSNR LichtFeld printed (in
`full-output.txt`) in LOG.md, round 2. The PSNR is for the log, not a published claim.

## If something stops

- **A flag is missing:** open `out\lichtfeld-help.txt`, find this build's name for it, change it in
  `train.ps1` (the `$needed` list and the arguments), run again.
- **The dry run fails to load the dataset:** keep `out\dry-output.txt` and stop; the folder layout
  (`images\` and `sparse\0\` with one PINHOLE camera) is what to question first.
- **Out of GPU memory:** run again with `-MaxCap 1000000`, then `-MaxCap 700000`.
- **It fails twice:** the fallbacks, in order, are gsplat on the laptop
  (`python simple_trainer.py mcmc --data_dir train --data_factor 1 --result_dir out\gsplat --strategy.cap-max 1500000`)
  and Brush on the Mac (`laptop/brush.sh`, once Brush is approved and installed). A rented GPU
  comes only after both, within the £6 cap.
