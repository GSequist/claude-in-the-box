package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/rs/zerolog"
	"envd-mini/internal/api"
	"envd-mini/internal/execcontext"
	publicport "envd-mini/internal/port"
	filesystemRpc "envd-mini/internal/services/filesystem"
	processRpc "envd-mini/internal/services/process"
	"envd-mini/internal/utils"
)

const (
	defaultPort         = 49983              // Port envd listens on
	portScannerInterval = 1000 * time.Millisecond // How often to scan for new localhost ports
	defaultUser         = "root"             // Default user for process execution
)

var (
	port int64 // Command-line flag: which port to listen on
)

func main() {
	// Parse command-line flags
	flag.Int64Var(&port, "port", defaultPort, "port on which the daemon should run")
	flag.Parse()

	// Create context for graceful shutdown
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// ========================================
	// STEP 1: Create execution defaults
	// ========================================
	// This stores default user and environment variables for processes
	defaults := &execcontext.Defaults{
		User:    defaultUser,
		EnvVars: utils.NewMap[string, string](), // Thread-safe map
	}

	// ========================================
	// STEP 2: Create logger
	// ========================================
	logger := zerolog.New(zerolog.ConsoleWriter{Out: log.Writer()}).
		With().
		Timestamp().
		Logger()

	// ========================================
	// STEP 3: Create HTTP router
	// ========================================
	m := chi.NewRouter()

	// ========================================
	// STEP 4: Register gRPC services
	// ========================================
	// Filesystem service: /filesystem.Filesystem/*
	// Handles: ListDir, Stat, MakeDir, Move, Remove
	fsLogger := logger.With().Str("service", "filesystem").Logger()
	filesystemRpc.Handle(m, &fsLogger, defaults)

	// Process service: /process.Process/*
	// Handles: Start, Signal, List
	processLogger := logger.With().Str("service", "process").Logger()
	processRpc.Handle(m, &processLogger, defaults)

	// ========================================
	// STEP 5: Register HTTP API endpoints
	// ========================================
	// Endpoints: GET /health, POST /init, GET /envs, GET/POST /files
	apiLogger := logger.With().Str("service", "api").Logger()
	service := api.New(&apiLogger, defaults) // Removed: mmdsChan, isNotFC
	handler := api.HandlerFromMux(service, m)

	// ========================================
	// STEP 6: Create HTTP server
	// ========================================
	server := &http.Server{
		Handler: handler,
		Addr:    fmt.Sprintf("0.0.0.0:%d", port),
	}

	// ========================================
	// STEP 7: Start port forwarding
	// ========================================
	// This auto-detects localhost ports and exposes them to VM IP using socat
	portScanner := publicport.NewScanner(portScannerInterval)
	defer portScanner.Destroy()

	portLogger := logger.With().Str("service", "port-forwarder").Logger()
	portForwarder := publicport.NewForwarder(&portLogger, portScanner)
	go portForwarder.StartForwarding(ctx) // Run in background
	go portScanner.ScanAndBroadcast()      // Run in background

	// ========================================
	// STEP 8: Start HTTP server (blocking)
	// ========================================
	logger.Info().Int64("port", port).Msg("Starting envd server")

	if err := server.ListenAndServe(); err != nil {
		log.Fatalf("Server error: %v", err)
	}
}
