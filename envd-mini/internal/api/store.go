package api

import (
	"encoding/json"
	"net/http"
	"sync"

	"github.com/rs/zerolog"

	"envd-mini/internal/execcontext"
	"envd-mini/internal/host"
	"envd-mini/internal/utils"
)

const (
	SigningReadOperation  = "read"
	SigningWriteOperation = "write"
)

type API struct {
	// Removed: isNotFC (not needed without MMDS)
	logger      *zerolog.Logger
	accessToken *string
	defaults    *execcontext.Defaults

	lastSetTime *utils.AtomicMax
	initLock    sync.Mutex
}

func New(l *zerolog.Logger, defaults *execcontext.Defaults) *API {
	return &API{
		logger:      l,
		defaults:    defaults,
		// Removed: mmdsChan, isNotFC
		lastSetTime: utils.NewAtomicMax(),
	}
}

func (a *API) GetHealth(w http.ResponseWriter, r *http.Request) {
	defer r.Body.Close()

	a.logger.Trace().Msg("Health check")

	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("Content-Type", "")

	w.WriteHeader(http.StatusNoContent)
}

func (a *API) GetMetrics(w http.ResponseWriter, r *http.Request) {
	defer r.Body.Close()

	a.logger.Trace().Msg("Get metrics")

	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("Content-Type", "application/json")

	metrics, err := host.GetMetrics()
	if err != nil {
		a.logger.Error().Err(err).Msg("Failed to get metrics")
		w.WriteHeader(http.StatusInternalServerError)

		return
	}

	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(metrics)
}

// validateSigning stub - no auth in our system
func (a *API) validateSigning(r *http.Request, signature *string, signatureExpiration *int, username *string, path string, operation string) error {
	// No access token = no validation needed
	return nil
}
