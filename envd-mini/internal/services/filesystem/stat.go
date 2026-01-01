package filesystem

import (
	"context"

	"connectrpc.com/connect"

	"envd-mini/internal/permissions"
	rpc "envd-mini/spec/grpc/envd/filesystem"
)

func (s Service) Stat(ctx context.Context, req *connect.Request[rpc.StatRequest]) (*connect.Response[rpc.StatResponse], error) {
	u, err := permissions.GetAuthUser(ctx, s.defaults.User)
	if err != nil {
		return nil, err
	}

	path, err := permissions.ExpandAndResolve(req.Msg.GetPath(), u, s.defaults.Workdir)
	if err != nil {
		return nil, connect.NewError(connect.CodeInvalidArgument, err)
	}

	entry, err := entryInfo(path)
	if err != nil {
		return nil, err
	}

	return connect.NewResponse(&rpc.StatResponse{Entry: entry}), nil
}
