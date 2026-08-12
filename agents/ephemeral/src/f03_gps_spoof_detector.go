package main

import (
	"encoding/json"
	"math"
	"os"
)

// f03_gps_spoof_detector — prüft GPS-Koordinaten auf Spoofing
// Entrypoint: fn run(params_json: &str) -> &str

type GPSReading struct {
	Lat       float64 `json:"lat"`
	Lon       float64 `json:"lon"`
	Tick      uint64  `json:"tick"`
	PrevTick  uint64  `json:"prev_tick"`
	PrevLat   float64 `json:"prev_lat"`
	PrevLon   float64 `json:"prev_lon"`
}

func main() {
	input := os.Args[1]
	var reading GPSReading
	if err := json.Unmarshal([]byte(input), &reading); err != nil {
		result, _ := json.Marshal(map[string]interface{}{"valid": false, "error": err.Error()})
		os.Stdout.Write(result)
		return
	}

	// Heuristics: movement > 1km in < 1 tick → spoofing
	deltaTick := reading.Tick - reading.PrevTick
	distance := haversine(reading.PrevLat, reading.PrevLon, reading.Lat, reading.Lon)
	suspicious := distance > 1.0 && deltaTick < 2

	result, _ := json.Marshal(map[string]interface{}{
		"valid":        !suspicious,
		"distance_km":  distance,
		"delta_tick":   deltaTick,
		"suspicious":   suspicious,
		"message":      "GPS spoof check complete",
		"f03_signature": "attested",
	})
	os.Stdout.Write(result)
}

func haversine(lat1, lon1, lat2, lon2 float64) float64 {
	const R = 6371.0 // km
	dLat := (lat2 - lat1) * math.Pi / 180.0
	dLon := (lon2 - lon1) * math.Pi / 180.0
	a := math.Sin(dLat/2)*math.Sin(dLat/2) +
		math.Cos(lat1*math.Pi/180.0)*math.Cos(lat2*math.Pi/180.0)*
			math.Sin(dLon/2)*math.Sin(dLon/2)
	c := 2 * math.Atan2(math.Sqrt(a), math.Sqrt(1-a))
	return R * c
}
