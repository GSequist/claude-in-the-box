package process

import (
	"context"

	"connectrpc.com/connect"

	rpc "envd-mini/spec/grpc/envd/process"
)

// Connect - stub (not used in our system)
func (s *Service) Connect(ctx context.Context, req *connect.Request[rpc.ConnectRequest], stream *connect.ServerStream[rpc.ConnectResponse]) error {
	return connect.NewError(connect.CodeUnimplemented, nil)
}

// SendInput - stub method (not used in our system)
func (s *Service) SendInput(ctx context.Context, req *connect.Request[rpc.SendInputRequest]) (*connect.Response[rpc.SendInputResponse], error) {
	return nil, connect.NewError(connect.CodeUnimplemented, nil)
}

// StreamInput - stub method (not used in our system)
func (s *Service) StreamInput(ctx context.Context, stream *connect.ClientStream[rpc.StreamInputRequest]) (*connect.Response[rpc.StreamInputResponse], error) {
	return nil, connect.NewError(connect.CodeUnimplemented, nil)
}

// Update - stub method (not used in our system)
func (s *Service) Update(ctx context.Context, req *connect.Request[rpc.UpdateRequest]) (*connect.Response[rpc.UpdateResponse], error) {
	return nil, connect.NewError(connect.CodeUnimplemented, nil)
}
