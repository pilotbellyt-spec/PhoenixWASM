use anyhow::{Context, Result};
use gex_cgen::{image, provider};
use std::{fs, path::Path};

fn main() -> Result<()> {
    let units = Path::new("units");
    let scratch = tempfile::tempdir_in(".build")?;
    gex_abi::set_mem_flavor(gex_abi::MemFlavor::M64);
    fs::create_dir_all(units.join("providers"))?;
    for p in provider::all() {
        if ["glibc_mem", "glibc_math"].contains(&p.name) {
            let (file, _) = provider::build(&p, scratch.path())?;
            fs::copy(
                &file,
                units.join("providers").join(file.file_name().unwrap()),
            )?;
        }
    }

    // The browser's default function tier uses this memory access mode in its key.
    image::set_unguarded(true);
    let bytes = fs::read(".build/libs/libxkbcommon.so.0").context("Run prepare.py first")?;
    let mut elf = gex_ld::elf::load(&bytes, 0x7160000).map_err(|e| anyhow::anyhow!("{e:?}"))?;
    gex_ld::elf::apply_own_relative(&mut elf);
    let program = gex_xlate::func::recover(&elf, Some(&bytes), &Default::default());
    let summaries = gex_xlate::summary::analyze(&program).map;
    let functions = program
        .functions
        .into_values()
        .filter(|f| {
            let name = f.name.as_deref().unwrap_or("");
            ["xkb_keysym_", "xkb_state_key_get_", "xkb_keymap_key_get_"]
                .iter()
                .any(|prefix| name.starts_with(prefix))
        })
        .collect();
    let functions = gex_cgen::select(functions, &Default::default(), &Default::default())?;
    anyhow::ensure!(
        !functions.is_empty(),
        "No keyboard lookup functions in this ELF"
    );
    let recovery = scratch.path().join("recovery");
    image::write_recovery(&recovery, &functions, &summaries, elf.class32)?;
    let work = scratch.path().join("work");
    fs::create_dir(&work)?;
    let wasm = scratch.path().join("c.wasm");
    let read = |addr| elf.segments.iter().find_map(|s| s.byte(addr));
    let stats = image::build_c_module(
        &recovery,
        &work,
        &scratch.path().join("objects"),
        &wasm,
        2,
        &read,
        &Default::default(),
        &Default::default(),
    )?;
    let dest = units.join(image::image_key(&elf));
    fs::create_dir_all(&dest)?;
    for file in ["c.entries", "c.wasm"] {
        fs::copy(scratch.path().join(file), dest.join(file))?;
    }
    println!(
        "{} keyboard functions, {} bytes",
        stats.functions, stats.wasm_bytes
    );
    Ok(())
}
