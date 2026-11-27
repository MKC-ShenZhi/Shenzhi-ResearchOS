package payment

import (
	"bytes"
	"context"
	"crypto"
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"math/big"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/wechatpay-apiv3/wechatpay-go/core"
	"github.com/wechatpay-apiv3/wechatpay-go/core/auth/verifiers"
	"github.com/wechatpay-apiv3/wechatpay-go/core/notify"
	"github.com/wechatpay-apiv3/wechatpay-go/services/payments"
)

type fakeGateway struct{ raw []byte }

func (f *fakeGateway) Create(ctx context.Context, order Order) (string, error) {
	return "weixin://test", nil
}
func (f *fakeGateway) Query(ctx context.Context, id string) (*Fact, error) {
	return &Fact{OrderID: id, Status: "pending"}, nil
}
func (f *fakeGateway) Verify(r *http.Request) (*Fact, error) {
	f.raw, _ = io.ReadAll(r.Body)
	return &Fact{Status: "paid"}, nil
}

func TestInternalCredentialAndRawTransport(t *testing.T) {
	gateway := &fakeGateway{}
	handler := Handler("test-token", gateway)
	body := `{ "resource" : "test bytes" }` + "\n"
	for _, token := range []string{"", "Bearer wrong", "Bearer test-token"} {
		request := httptest.NewRequest("POST", "/internal/wechat/verify-notification", strings.NewReader(body))
		request.Header.Set("Authorization", token)
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)
		expected := 401
		if token == "Bearer test-token" {
			expected = 200
		}
		if response.Code != expected {
			t.Fatalf("status %d, expected %d", response.Code, expected)
		}
	}
	if !bytes.Equal(gateway.raw, []byte(body)) {
		t.Fatal("raw body changed")
	}
	for _, body := range []string{`{"amount":1}`, `{"order_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","amount":1,"currency":"USD","description":"test"}`} {
		request := httptest.NewRequest("POST", "/internal/wechat/orders", strings.NewReader(body))
		request.Header.Set("Authorization", "Bearer test-token")
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)
		if response.Code != 400 {
			t.Fatal("invalid order accepted")
		}
	}
}

func TestDisabledSDKStartsWithoutMerchantCredentials(t *testing.T) {
	sdk, err := NewSDK(context.Background(), Config{Token: "test"})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := sdk.Create(context.Background(), Order{}); err == nil {
		t.Fatal("disabled SDK created order")
	}
	if _, err := NewSDK(context.Background(), Config{}); err == nil {
		t.Fatal("missing internal token accepted")
	}
}

func TestTransactionIdentityAndState(t *testing.T) {
	sdk := &SDK{config: Config{AppID: "test-app", MerchantID: "test-merchant"}}
	transaction := &payments.Transaction{Appid: core.String("test-app"), Mchid: core.String("test-merchant"),
		OutTradeNo: core.String(strings.Repeat("a", 32)), TransactionId: core.String("test-tx"), TradeState: core.String("SUCCESS"),
		Amount: &payments.TransactionAmount{Total: core.Int64(123), Currency: core.String("CNY")}}
	fact, err := sdk.fact(transaction)
	if err != nil || fact.Status != "paid" || fact.Amount != 123 {
		t.Fatalf("invalid fact: %v", err)
	}
	transaction.Mchid = core.String("other")
	if _, err = sdk.fact(transaction); err == nil {
		t.Fatal("wrong merchant accepted")
	}
}

func TestOfficialSDKNotificationVerificationAndDecryption(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now()
	template := &x509.Certificate{SerialNumber: big.NewInt(12345), Subject: pkix.Name{CommonName: "test"},
		NotBefore: now.Add(-time.Hour), NotAfter: now.Add(time.Hour), KeyUsage: x509.KeyUsageDigitalSignature}
	der, err := x509.CreateCertificate(rand.Reader, template, template, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	certificate, err := x509.ParseCertificate(der)
	if err != nil {
		t.Fatal(err)
	}
	apiKey := "01234567890123456789012345678901"
	visitor := core.NewCertificateMapWithList([]*x509.Certificate{certificate})
	sdk := &SDK{config: Config{AppID: "test-app", MerchantID: "test-merchant"},
		notify: notify.NewNotifyHandler(apiKey, verifiers.NewSHA256WithRSAVerifier(visitor))}
	transaction := `{"appid":"test-app","mchid":"test-merchant","out_trade_no":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","transaction_id":"test-tx","trade_state":"SUCCESS","amount":{"total":123,"currency":"CNY"}}`
	block, err := aes.NewCipher([]byte(apiKey))
	if err != nil {
		t.Fatal(err)
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		t.Fatal(err)
	}
	resourceNonce := "012345678901"
	encrypted := gcm.Seal(nil, []byte(resourceNonce), []byte(transaction), []byte("transaction"))
	body, _ := json.Marshal(map[string]any{"id": "test-notification", "create_time": now.Format(time.RFC3339),
		"event_type": "TRANSACTION.SUCCESS", "resource_type": "encrypt-resource", "summary": "test",
		"resource": map[string]string{"algorithm": "AEAD_AES_256_GCM", "ciphertext": base64.StdEncoding.EncodeToString(encrypted),
			"nonce": resourceNonce, "associated_data": "transaction", "original_type": "transaction"}})
	timestamp := strconv.FormatInt(now.Unix(), 10)
	nonce := "test-signature-nonce"
	message := fmt.Sprintf("%s\n%s\n%s\n", timestamp, nonce, body)
	hash := sha256.Sum256([]byte(message))
	signature, err := rsa.SignPKCS1v15(rand.Reader, key, crypto.SHA256, hash[:])
	if err != nil {
		t.Fatal(err)
	}
	request := func(body []byte) *http.Request {
		r := httptest.NewRequest("POST", "/internal/wechat/verify-notification", bytes.NewReader(body))
		r.Header.Set("Wechatpay-Timestamp", timestamp)
		r.Header.Set("Wechatpay-Nonce", nonce)
		r.Header.Set("Wechatpay-Serial", strings.ToUpper(certificate.SerialNumber.Text(16)))
		r.Header.Set("Wechatpay-Signature", base64.StdEncoding.EncodeToString(signature))
		return r
	}
	fact, err := sdk.Verify(request(body))
	if err != nil || fact.Amount != 123 || fact.Status != "paid" {
		t.Fatalf("SDK verification/decryption failed: %v", err)
	}
	if _, err := sdk.Verify(request(append(body, ' '))); err == nil {
		t.Fatal("tampered signature accepted")
	}
	forged := request(body)
	forged.Header.Set("Wechatpay-Signature", "invalid")
	if _, err := sdk.Verify(forged); err == nil {
		t.Fatal("forged notification accepted")
	}
}
