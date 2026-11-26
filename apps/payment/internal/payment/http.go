package payment

import (
	"crypto/subtle"
	"encoding/json"
	"net/http"
	"regexp"
)

var orderID = regexp.MustCompile(`^[a-f0-9]{32}$`)

func Handler(token string, gateway Gateway) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) { writeJSON(w, map[string]string{"status": "ok"}) })
	internal := http.NewServeMux()
	internal.HandleFunc("POST /internal/wechat/orders", func(w http.ResponseWriter, r *http.Request) {
		var order Order
		if err := json.NewDecoder(r.Body).Decode(&order); err != nil || !orderID.MatchString(order.OrderID) || order.Amount <= 0 || order.Currency != "CNY" || order.Description == "" {
			http.Error(w, "invalid order", http.StatusBadRequest)
			return
		}
		url, err := gateway.Create(r.Context(), order)
		if err != nil {
			http.Error(w, "wechat create failed", http.StatusBadGateway)
			return
		}
		writeJSON(w, map[string]string{"kind": "qr", "code_url": url})
	})
	internal.HandleFunc("GET /internal/wechat/orders/{id}", func(w http.ResponseWriter, r *http.Request) {
		id := r.PathValue("id")
		if !orderID.MatchString(id) {
			http.Error(w, "invalid order id", http.StatusBadRequest)
			return
		}
		fact, err := gateway.Query(r.Context(), id)
		if err != nil {
			http.Error(w, "wechat query failed", http.StatusBadGateway)
			return
		}
		writeJSON(w, fact)
	})
	internal.HandleFunc("POST /internal/wechat/verify-notification", func(w http.ResponseWriter, r *http.Request) {
		fact, err := gateway.Verify(r)
		if err != nil {
			http.Error(w, "notification rejected", http.StatusBadRequest)
			return
		}
		writeJSON(w, fact)
	})
	mux.Handle("/internal/", http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if token == "" || subtle.ConstantTimeCompare([]byte(r.Header.Get("Authorization")), []byte("Bearer "+token)) != 1 {
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		r.Body = http.MaxBytesReader(w, r.Body, 1<<20)
		internal.ServeHTTP(w, r)
	}))
	return mux
}

func writeJSON(w http.ResponseWriter, value any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(value)
}
