use rosetta_connect_rust_canary::experimentation::assignment::v1::{
    ASSIGNMENT_SERVICE_GET_ASSIGNMENT_SPEC, ASSIGNMENT_SERVICE_STREAM_CONFIG_UPDATES_SPEC,
    AssignmentService, AssignmentServiceClient, GetAssignmentRequest, StreamConfigUpdatesRequest,
};

#[allow(dead_code)]
fn assert_generated_handler_trait<S: AssignmentService>() {}

#[allow(dead_code)]
fn assert_generated_client_methods<T>(client: &AssignmentServiceClient<T>)
where
    T: connectrpc::client::ClientTransport,
    <T::ResponseBody as http_body::Body>::Error: std::fmt::Display,
{
    let _unary_future = client.get_assignment(GetAssignmentRequest::default());
    let _server_streaming_future =
        client.stream_config_updates(StreamConfigUpdatesRequest::default());
}

#[test]
fn generated_service_contains_unary_and_server_streaming_procedures() {
    assert_eq!(
        ASSIGNMENT_SERVICE_GET_ASSIGNMENT_SPEC.stream_type,
        connectrpc::StreamType::Unary,
    );
    assert_eq!(
        ASSIGNMENT_SERVICE_STREAM_CONFIG_UPDATES_SPEC.stream_type,
        connectrpc::StreamType::ServerStream,
    );
}
