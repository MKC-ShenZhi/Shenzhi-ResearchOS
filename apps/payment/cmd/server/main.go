package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"time"

	"shenzhi/payment/internal/payment"
)

func main() {
	if len(os.Args) > 1 && os.Args[1] == "healthcheck" {
		client := &http.Client{Timeout: 3 * time.Second}
		response, err := client.Get("http://127.0.0.1:8090/health")
		if err != nil {
			os.Exit(1)
		}
		defer response.Body.Close()
		if response.StatusCode != http.StatusOK {
			os.Exit(1)
		}
		return
	}
	config := payment.FromEnv()
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	sdk, err := payment.NewSDK(ctx, config)
	if err != nil {
		log.Fatal("payment SDK configuration failed")
	}
	server := &http.Server{Addr: ":8090", Handler: payment.Handler(config.Token, sdk),
		ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 25 * time.Second, WriteTimeout: 25 * time.Second, IdleTimeout: 60 * time.Second}
	log.Fatal(server.ListenAndServe())
}
