package filesystem

import (
	"context"
	"sync"

	"connectrpc.com/connect"

	rpc "envd-mini/spec/grpc/envd/filesystem"
)

// FileWatcher - stub structure (file watching not used)
type FileWatcher struct {
	Events []*rpc.FilesystemEvent
	Error  error
	Lock   sync.Mutex
}

// CreateWatcher - stub method (not used in our system)
func (s Service) CreateWatcher(ctx context.Context, req *connect.Request[rpc.CreateWatcherRequest]) (*connect.Response[rpc.CreateWatcherResponse], error) {
	return nil, connect.NewError(connect.CodeUnimplemented, nil)
}

// GetWatcherEvents - stub method (not used in our system)
func (s Service) GetWatcherEvents(ctx context.Context, req *connect.Request[rpc.GetWatcherEventsRequest]) (*connect.Response[rpc.GetWatcherEventsResponse], error) {
	return nil, connect.NewError(connect.CodeUnimplemented, nil)
}

// RemoveWatcher - stub method (not used in our system)
func (s Service) RemoveWatcher(ctx context.Context, req *connect.Request[rpc.RemoveWatcherRequest]) (*connect.Response[rpc.RemoveWatcherResponse], error) {
	return nil, connect.NewError(connect.CodeUnimplemented, nil)
}

// WatchDir - stub method (not used in our system)  
func (s Service) WatchDir(ctx context.Context, req *connect.Request[rpc.WatchDirRequest], stream *connect.ServerStream[rpc.WatchDirResponse]) error {
	return connect.NewError(connect.CodeUnimplemented, nil)
}
