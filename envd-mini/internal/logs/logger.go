package logs

import (
	"io"
	"os"
	"time"

	"github.com/rs/zerolog"

	// Removed: "envd-mini/internal/host" (only used for MMDS)
	// Removed: "envd-mini/internal/logs/exporter" (deleted - was for MMDS log collection)
)

// Simplified: No MMDS, no HTTP log exporter, just stdout
func NewLogger() *zerolog.Logger {
	zerolog.TimestampFieldName = "timestamp"
	zerolog.TimeFieldFormat = time.RFC3339Nano

	l := zerolog.
		New(io.MultiWriter(os.Stdout)).
		With().
		Timestamp().
		Logger().
		Level(zerolog.DebugLevel)

	return &l
}
