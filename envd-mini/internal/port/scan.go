package port

import (
	"time"

	"github.com/rs/zerolog"
	"github.com/shirou/gopsutil/v4/net"

	"envd-mini/internal/utils"
)

type Scanner struct {
	Processes chan net.ConnectionStat
	scanExit  chan struct{}
	subs      *utils.Map[string, *ScannerSubscriber] // Changed from smap.Map to utils.Map
	period    time.Duration
}

func (s *Scanner) Destroy() {
	close(s.scanExit)
}

func NewScanner(period time.Duration) *Scanner {
	return &Scanner{
		period:    period,
		subs:      utils.NewMap[string, *ScannerSubscriber](), // Changed from smap.New
		scanExit:  make(chan struct{}),
		Processes: make(chan net.ConnectionStat),
	}
}

func (s *Scanner) AddSubscriber(logger *zerolog.Logger, id string, filter *ScannerFilter) *ScannerSubscriber {
	subscriber := NewScannerSubscriber(logger, id, filter)
	s.subs.Store(id, subscriber) // Changed from Insert to Store

	return subscriber
}

func (s *Scanner) Unsubscribe(sub *ScannerSubscriber) {
	s.subs.Delete(sub.ID()) // Changed from Remove to Delete
	sub.Destroy()
}

// ScanAndBroadcast starts scanning open TCP ports and broadcasts every open port to all subscribers.
func (s *Scanner) ScanAndBroadcast() {
	for {
		// tcp monitors both ipv4 and ipv6 connections.
		processes, _ := net.Connections("tcp")
		// Iterate over all subscribers
		s.subs.Range(func(key string, sub *ScannerSubscriber) bool {
			sub.Signal(processes)
			return true // continue iteration
		})
		select {
		case <-s.scanExit:
			return
		default:
			time.Sleep(s.period)
		}
	}
}
