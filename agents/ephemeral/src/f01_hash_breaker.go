package main

import (
	"encoding/json"
	"math"
	"os"
)

// f01_hash_breaker — prüft BHO-Invarianten (hours*rate == total) mit Toleranz 0.01
// Entrypoint: fn run(params_json: &str) -> &str

type InvariantCheck struct {
	ProjectID string  `json:"project_id"`
	Hours     float64 `json:"hours"`
	Rate      float64 `json:"rate"`
	Total     float64 `json:"total"`
}

func main() {
	input := os.Args[1]
	var check InvariantCheck
	if err := json.Unmarshal([]byte(input), &check); err != nil {
		result, _ := json.Marshal(map[string]interface{}{"valid": false, "error": err.Error()})
		os.Stdout.Write(result)
		return
	}

	expected := check.Hours * check.Rate
	delta := math.Abs(check.Total - expected)
	valid := delta < 0.01

	result, _ := json.Marshal(map[string]interface{}{
		"valid":        valid,
		"delta":        delta,
		"expected":     expected,
		"actual":       check.Total,
		"message":      "Hash breaker executed",
		"f01_signature": "attested",
	})
	os.Stdout.Write(result)
}
