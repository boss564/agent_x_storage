package main

import (
	"encoding/json"
	"log"
	"math/rand"
	"os"
	"strconv"
	"time"

	"github.com/nats-io/nats.go"
)

type PoisonEvent struct {
	TxID        string `json:"tx_id"`
	Constraints int    `json:"constraints"`
	Data        string `json:"data"`
	Schema      string `json:"schema"`
	DeviceID    string `json:"device_id"`
	Amount      int    `json:"amount"`
}

func main() {
	natsURL := os.Getenv("NATS_URL")
	if natsURL == "" {
		natsURL = "nats://nats:4222"
	}
	intervalMS := getEnvAsInt("POISON_INTERVAL_MS", 500)
	burst := getEnvAsInt("POISON_BURST", 5)

	nc, err := nats.Connect(natsURL)
	if err != nil {
		log.Fatalf("❌ [F09] Konnte nicht zu NATS verbinden: %v", err)
	}
	defer nc.Close()
	log.Printf("☠️ [F09] Poison-Injector gestartet. NATS: %s, Burst: %d, Intervall: %dms", natsURL, burst, intervalMS)

	rand.Seed(time.Now().UnixNano())

	for {
		payload := createPoisonPayload()

		for i := 0; i < burst; i++ {
			if err := nc.Publish("agentx.surface.events", payload); err != nil {
				log.Printf("⚠️ Fehler beim Injecten: %v", err)
			} else {
				log.Printf("☠️ [F09] Gift injiziert (Part %d/%d)", i+1, burst)
			}
			time.Sleep(50 * time.Millisecond)
		}
		time.Sleep(time.Duration(intervalMS) * time.Millisecond)
	}
}

func createPoisonPayload() []byte {
	event := PoisonEvent{
		TxID:        "poison-" + time.Now().Format("150405.000000"),
		Constraints: 1 << 22, // 4.194.304 — DEADLY constraint bloat
		Data:        randomString(64 * 1024),
		Schema:      "COMPLIANCE",
		DeviceID:    "0xPOISON_SOURCE",
		Amount:      999999999,
	}
	b, _ := json.Marshal(event)
	return b
}

func randomString(length int) string {
	const charset = "abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()_+-=[]{}|;:,.<>?/~"
	b := make([]byte, length)
	for i := range b {
		b[i] = charset[rand.Intn(len(charset))]
	}
	return string(b)
}

func getEnvAsInt(key string, defaultVal int) int {
	if val, exists := os.LookupEnv(key); exists {
		if i, err := strconv.Atoi(val); err == nil {
			return i
		}
	}
	return defaultVal
}
