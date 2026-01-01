package process

import (
	"context"

	"connectrpc.com/connect"

	"envd-mini/internal/services/process/handler"
	rpc "envd-mini/spec/grpc/envd/process"
)

func (s *Service) List(context.Context, *connect.Request[rpc.ListRequest]) (*connect.Response[rpc.ListResponse], error) {
	processes := make([]*rpc.ProcessInfo, 0)

	s.processes.Range(func(pid uint32, value *handler.Handler) bool {
		processes = append(processes, &rpc.ProcessInfo{
			Pid:    pid,
			Tag:    value.Tag,
			Config: value.Config,
		})

		return true
	})

	return connect.NewResponse(&rpc.ListResponse{
		Processes: processes,
	}), nil
}
