use buffa::Message;
use rosetta_connect_rust_canary::kaizen::audience::v1::{AudienceContext, AudienceRule};
use serde::{Deserialize, de::DeserializeOwned};
use std::{fmt::Debug, fs};

const EXPECTED_CORPUS_ROWS: usize = 30;
const EXPECTED_TYPED_VECTORS: usize = EXPECTED_CORPUS_ROWS * 2;

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct Fixture {
    expected_wire: ExpectedWire,
}

#[derive(Deserialize)]
struct ExpectedWire {
    rule: WireVector,
    context: WireVector,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct WireVector {
    binary_hex: String,
    canonical_proto_json: String,
}

fn fixtures() -> Vec<Fixture> {
    let path = std::env::var("ROSETTA_CONFORMANCE_FILE")
        .expect("ROSETTA_CONFORMANCE_FILE identifies the audience corpus");
    let contents = fs::read_to_string(path).expect("audience corpus is readable");
    let fixtures = contents
        .lines()
        .filter(|line| !line.trim().is_empty())
        .map(|line| serde_json::from_str(line).expect("audience corpus row is valid JSON"))
        .collect::<Vec<_>>();
    assert_eq!(fixtures.len(), EXPECTED_CORPUS_ROWS);
    fixtures
}

fn assert_binary<M>(hex_input: &str)
where
    M: Message + Debug,
{
    let bytes = hex::decode(hex_input).expect("valid lowercase hex fixture");
    let decoded = M::decode_from_slice(&bytes).expect("Buffa decodes corpus bytes");
    let redecoded =
        M::decode_from_slice(&decoded.encode_to_vec()).expect("Buffa decodes its own output");
    assert_eq!(decoded, redecoded);
}

fn assert_protojson<M>(binary_hex: &str, canonical_json: &str)
where
    M: Message + serde::Serialize + DeserializeOwned + Debug,
{
    let bytes = hex::decode(binary_hex).expect("valid lowercase hex fixture");
    let from_binary = M::decode_from_slice(&bytes).expect("Buffa decodes corpus bytes");
    let value = serde_json::to_value(&from_binary).expect("Buffa serializes typed ProtoJSON");
    let canonical = serde_json_canonicalizer::to_string(&value)
        .expect("typed ProtoJSON canonicalizes successfully");
    assert_eq!(canonical, canonical_json);

    let from_json: M =
        serde_json::from_str(canonical_json).expect("Buffa decodes canonical ProtoJSON");
    assert_eq!(from_json, from_binary);
}

#[test]
fn audience_binary_vectors_round_trip_semantically() {
    let fixtures = fixtures();
    for fixture in &fixtures {
        assert_binary::<AudienceRule>(&fixture.expected_wire.rule.binary_hex);
        assert_binary::<AudienceContext>(&fixture.expected_wire.context.binary_hex);
    }

    assert_eq!(fixtures.len() * 2, EXPECTED_TYPED_VECTORS);
}

#[test]
fn audience_protojson_vectors_are_canonical_and_semantic() {
    let fixtures = fixtures();
    for fixture in &fixtures {
        assert_protojson::<AudienceRule>(
            &fixture.expected_wire.rule.binary_hex,
            &fixture.expected_wire.rule.canonical_proto_json,
        );
        assert_protojson::<AudienceContext>(
            &fixture.expected_wire.context.binary_hex,
            &fixture.expected_wire.context.canonical_proto_json,
        );
    }

    assert_eq!(fixtures.len() * 2, EXPECTED_TYPED_VECTORS);
}
