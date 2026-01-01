package filesystem

import (
	"connectrpc.com/connect"
	"github.com/go-chi/chi/v5"
	"github.com/rs/zerolog"

	"envd-mini/internal/execcontext"
	"envd-mini/internal/logs"
	// Removed: "envd-mini/internal/services/legacy" (backwards compat for old E2B SDK)
	spec "envd-mini/spec/grpc/envd/filesystem/filesystemconnect"
	"envd-mini/internal/utils"
)

type Service struct {
	logger   *zerolog.Logger
	watchers *utils.Map[string, *FileWatcher]
	defaults *execcontext.Defaults
}

func Handle(server *chi.Mux, l *zerolog.Logger, defaults *execcontext.Defaults) {
	service := Service{
		logger:   l,
		watchers: utils.NewMap[string, *FileWatcher](),
		defaults: defaults,
	}

	interceptors := connect.WithInterceptors(
		logs.NewUnaryLogInterceptor(l),
		// Removed: legacy.Convert() (we don't use old E2B Python SDK)
	)

	path, handler := spec.NewFilesystemHandler(service, interceptors)

	server.Mount(path, handler)
}
