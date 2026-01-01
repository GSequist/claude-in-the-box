package utils

import "sync"

type Map[K comparable, V any] struct {
	m sync.Map
}

func NewMap[K comparable, V any]() *Map[K, V] {
	return &Map[K, V]{
		m: sync.Map{},
	}
}

// Claude lecture:
// Python equivalent:

// PYTHON:

// from typing import TypeVar, Generic

// K = TypeVar('K')
// V = TypeVar('V')

// # Define class
// class Map(Generic[K, V]):
// 	def __init__(self):
// 		self.m = {}

// 	def store(self, key: K, value: V):
// 		self.m[key] = value

// 	def load(self, key: K) -> V | None:
// 		return self.m.get(key)

// # Factory function
// def new_map() -> Map[K, V]:
// 	return Map()

// # Usage:
// env_vars = new_map()  # Map[str, str]
// env_vars.store("API_KEY", "secret123")
// print(env_vars.load("API_KEY"))  # "secret123"

// GO:

// package utils

// import "sync"

// // Define struct (class)
// type Map[K comparable, V any] struct {
// 	m sync.Map  // Thread-safe map
// }

// // Method: Store (like self.store in Python)
// func (m *Map[K, V]) Store(key K, value V) {
// 	m.m.Store(key, value)
// }

// // Method: Load (like self.load in Python)
// func (m *Map[K, V]) Load(key K) (V, bool) {
// 	v, ok := m.m.Load(key)
// 	if !ok {
// 		var zero V  // Zero value of type V
// 		return zero, false
// 	}
// 	return v.(V), true  // Type assertion
// }

// // Factory function
// func NewMap[K comparable, V any]() *Map[K, V] {
// 	return &Map[K, V]{
// 		m: sync.Map{},
// 	}
// }

// // Usage:
// envVars := utils.NewMap[string, string]()
// envVars.Store("API_KEY", "secret123")
// value, ok := envVars.Load("API_KEY")  // value = "secret123", ok = true

func (m *Map[K, V]) Delete(key K) {
	m.m.Delete(key)
}

func (m *Map[K, V]) Load(key K) (value V, ok bool) {
	v, ok := m.m.Load(key)
	if !ok {
		return value, ok
	}

	return v.(V), ok
}

func (m *Map[K, V]) LoadAndDelete(key K) (value V, loaded bool) {
	v, loaded := m.m.LoadAndDelete(key)
	if !loaded {
		return value, loaded
	}

	return v.(V), loaded
}

func (m *Map[K, V]) LoadOrStore(key K, value V) (actual V, loaded bool) {
	a, loaded := m.m.LoadOrStore(key, value)

	return a.(V), loaded
}

func (m *Map[K,V]) Range(f func(key K, value V) bool) {
	typed := func(key any, value any) bool {
		return f(key.(K), value.(V))
	}
	m.m.Range(typed)
}

func (m *Map[K, V]) Store(key K, value V) {
	m.m.Store(key, value)
}
