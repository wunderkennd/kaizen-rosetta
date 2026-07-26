use std::{env, path::PathBuf};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let proto_root = PathBuf::from(env::var("ROSETTA_PROTO_ROOT")?);
    let mut protos = walkdir::WalkDir::new(&proto_root)
        .into_iter()
        .collect::<Result<Vec<_>, _>>()?
        .into_iter()
        .filter(|entry| entry.file_type().is_file())
        .map(|entry| entry.into_path())
        .filter(|path| path.extension().is_some_and(|ext| ext == "proto"))
        .collect::<Vec<_>>();
    protos.sort();
    if protos.is_empty() {
        return Err("immutable Rosetta export contains no .proto files".into());
    }
    println!("cargo:rerun-if-env-changed=ROSETTA_PROTO_ROOT");
    connectrpc_build::Config::new()
        .files(&protos)
        .includes(&[proto_root])
        .include_file("_connectrpc.rs")
        .compile()?;
    Ok(())
}
