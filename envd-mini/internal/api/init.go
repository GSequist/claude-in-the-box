package api

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/rs/zerolog"
	"golang.org/x/sys/unix"
)

var ErrAccessTokenAlreadySet = errors.New("access token is already set")

const (
	maxTimeInPast   = 50 * time.Millisecond
	maxTimeInFuture = 5 * time.Second
)

func (a *API) PostInit(w http.ResponseWriter, r *http.Request) {
	defer r.Body.Close()

	// Use logger directly (no operation ID needed for our simple use case)
	logger := *a.logger

	if r.Body != nil {
		var initRequest PostInitJSONBody

		err := json.NewDecoder(r.Body).Decode(&initRequest)
		if err != nil && !errors.Is(err, io.EOF) {
			logger.Error().Msgf("Failed to decode request: %v", err)
			w.WriteHeader(http.StatusBadRequest)

			return
		}

		a.initLock.Lock()
		defer a.initLock.Unlock()

		// Update data only if the request is newer or if there's no timestamp at all
		if initRequest.Timestamp == nil || a.lastSetTime.SetToGreater(initRequest.Timestamp.UnixNano()) {
			err = a.SetData(logger, initRequest)
			if err != nil {
				switch {
				case errors.Is(err, ErrAccessTokenAlreadySet):
					w.WriteHeader(http.StatusConflict)
				default:
					logger.Error().Msgf("Failed to set data: %v", err)
					w.WriteHeader(http.StatusBadRequest)
				}
				w.Write([]byte(err.Error()))

				return
			}
		}
	}

	// Removed MMDS polling - we don't use Firecracker metadata service

	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("Content-Type", "")

	w.WriteHeader(http.StatusNoContent)
}

func (a *API) SetData(logger zerolog.Logger, data PostInitJSONBody) error {
	if data.Timestamp != nil {
		// Check if current time differs significantly from the received timestamp
		if shouldSetSystemTime(time.Now(), *data.Timestamp) {
			logger.Debug().Msgf("Setting sandbox start time to: %v", *data.Timestamp)
			ts := unix.NsecToTimespec(data.Timestamp.UnixNano())
			err := unix.ClockSettime(unix.CLOCK_REALTIME, &ts)
			if err != nil {
				logger.Error().Msgf("Failed to set system time: %v", err)
			}
		} else {
			logger.Debug().Msgf("Current time is within acceptable range of timestamp %v, not setting system time", *data.Timestamp)
		}
	}

	if data.EnvVars != nil {
		logger.Debug().Msg(fmt.Sprintf("Setting %d env vars", len(*data.EnvVars)))

		for key, value := range *data.EnvVars {
			logger.Debug().Msgf("Setting env var for %s", key)
			a.defaults.EnvVars.Store(key, value)
		}
	}

	if data.AccessToken != nil {
		if a.accessToken != nil && *data.AccessToken != *a.accessToken {
			logger.Error().Msg("Access token is already set and cannot be changed")

			return ErrAccessTokenAlreadySet
		}

		logger.Debug().Msg("Setting access token")
		a.accessToken = data.AccessToken
	}

	if data.DefaultUser != nil && *data.DefaultUser != "" {
		logger.Debug().Msgf("Setting default user to: %s", *data.DefaultUser)
		a.defaults.User = *data.DefaultUser
	}

	if data.DefaultWorkdir != nil && *data.DefaultWorkdir != "" {
		logger.Debug().Msgf("Setting default workdir to: %s", *data.DefaultWorkdir)
		a.defaults.Workdir = data.DefaultWorkdir
	}

	return nil
}

// shouldSetSystemTime returns true if the current time differs significantly from the received timestamp,
// indicating the system clock should be adjusted. Returns true when the sandboxTime is more than
// maxTimeInPast before the hostTime or more than maxTimeInFuture after the hostTime.
func shouldSetSystemTime(sandboxTime, hostTime time.Time) bool {
	return sandboxTime.Before(hostTime.Add(-maxTimeInPast)) || sandboxTime.After(hostTime.Add(maxTimeInFuture))
}
