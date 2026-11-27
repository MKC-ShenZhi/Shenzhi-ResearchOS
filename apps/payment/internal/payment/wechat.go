// Package payment adapts the official SDK only; no users, database or fulfillment.
package payment

import (
	"context"
	"errors"
	"net/http"
	"os"
	"time"

	"github.com/wechatpay-apiv3/wechatpay-go/core"
	"github.com/wechatpay-apiv3/wechatpay-go/core/auth/verifiers"
	"github.com/wechatpay-apiv3/wechatpay-go/core/downloader"
	"github.com/wechatpay-apiv3/wechatpay-go/core/notify"
	"github.com/wechatpay-apiv3/wechatpay-go/core/option"
	"github.com/wechatpay-apiv3/wechatpay-go/services/payments"
	"github.com/wechatpay-apiv3/wechatpay-go/services/payments/native"
	"github.com/wechatpay-apiv3/wechatpay-go/utils"
)

type Config struct {
	Enabled                                                             bool
	Token, AppID, MerchantID, Serial, APIKey, PrivateKeyFile, NotifyURL string
}

func FromEnv() Config {
	return Config{Enabled: os.Getenv("WECHAT_ENABLED") == "true", Token: os.Getenv("PAYMENT_SERVICE_TOKEN"),
		AppID: os.Getenv("WECHAT_APP_ID"), MerchantID: os.Getenv("WECHAT_MCH_ID"), Serial: os.Getenv("WECHAT_CERT_SERIAL"),
		APIKey: os.Getenv("WECHAT_API_V3_KEY"), PrivateKeyFile: os.Getenv("WECHAT_PRIVATE_KEY_FILE"), NotifyURL: os.Getenv("WECHAT_NOTIFY_URL")}
}

type Order struct {
	OrderID     string `json:"order_id"`
	Amount      int64  `json:"amount"`
	Currency    string `json:"currency"`
	Description string `json:"description"`
}

type Fact struct {
	OrderID       string `json:"order_id"`
	TransactionID string `json:"transaction_id"`
	Amount        int64  `json:"amount"`
	Currency      string `json:"currency"`
	MerchantID    string `json:"merchant_id"`
	AppID         string `json:"app_id"`
	Status        string `json:"status"`
}

type Gateway interface {
	Create(context.Context, Order) (string, error)
	Query(context.Context, string) (*Fact, error)
	Verify(*http.Request) (*Fact, error)
}

type SDK struct {
	config Config
	native *native.NativeApiService
	notify *notify.Handler
}

func NewSDK(ctx context.Context, config Config) (*SDK, error) {
	if config.Token == "" {
		return nil, errors.New("internal credential required")
	}
	sdk := &SDK{config: config}
	if !config.Enabled {
		return sdk, nil
	} // Credential-free startup in Mock installations.
	if config.AppID == "" || config.MerchantID == "" || config.Serial == "" || len(config.APIKey) != 32 || config.NotifyURL == "" {
		return nil, errors.New("wechat configuration missing")
	}
	key, err := utils.LoadPrivateKeyWithPath(config.PrivateKeyFile)
	if err != nil {
		return nil, err
	}
	client, err := core.NewClient(ctx,
		option.WithWechatPayAutoAuthCipher(config.MerchantID, config.Serial, key, config.APIKey),
		option.WithHTTPClient(&http.Client{Timeout: 15 * time.Second}))
	if err != nil {
		return nil, err
	}
	sdk.native = &native.NativeApiService{Client: client}
	visitor := downloader.MgrInstance().GetCertificateVisitor(config.MerchantID)
	sdk.notify = notify.NewNotifyHandler(config.APIKey, verifiers.NewSHA256WithRSAVerifier(visitor))
	return sdk, nil
}

func (s *SDK) Create(ctx context.Context, order Order) (string, error) {
	if s.native == nil {
		return "", errors.New("wechat disabled")
	}
	response, _, err := s.native.Prepay(ctx, native.PrepayRequest{
		Appid: core.String(s.config.AppID), Mchid: core.String(s.config.MerchantID),
		Description: core.String(order.Description), OutTradeNo: core.String(order.OrderID),
		NotifyUrl: core.String(s.config.NotifyURL),
		Amount:    &native.Amount{Total: core.Int64(order.Amount), Currency: core.String(order.Currency)},
	})
	if err != nil {
		return "", err
	}
	if response.CodeUrl == nil {
		return "", errors.New("missing code url")
	}
	return *response.CodeUrl, nil
}

func (s *SDK) Query(ctx context.Context, id string) (*Fact, error) {
	if s.native == nil {
		return nil, errors.New("wechat disabled")
	}
	transaction, _, err := s.native.QueryOrderByOutTradeNo(ctx, native.QueryOrderByOutTradeNoRequest{
		Mchid: core.String(s.config.MerchantID), OutTradeNo: core.String(id),
	})
	if core.IsAPIError(err, "ORDER_NOT_EXIST") {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return s.fact(transaction)
}

func (s *SDK) Verify(request *http.Request) (*Fact, error) {
	if s.notify == nil {
		return nil, errors.New("wechat disabled")
	}
	transaction := new(payments.Transaction)
	notification, err := s.notify.ParseNotifyRequest(request.Context(), request, transaction)
	if err != nil {
		return nil, err
	}
	if notification.EventType != "TRANSACTION.SUCCESS" {
		return nil, errors.New("unsupported event")
	}
	return s.fact(transaction)
}

func (s *SDK) fact(t *payments.Transaction) (*Fact, error) {
	if t == nil || t.OutTradeNo == nil || t.Mchid == nil || t.Appid == nil || t.Amount == nil ||
		t.Amount.Total == nil || t.Amount.Currency == nil || t.TradeState == nil ||
		*t.Mchid != s.config.MerchantID || *t.Appid != s.config.AppID || *t.Amount.Currency != "CNY" {
		return nil, errors.New("invalid transaction")
	}
	state := "pending"
	switch *t.TradeState {
	case "SUCCESS":
		state = "paid"
	case "CLOSED", "REVOKED", "PAYERROR":
		state = "closed"
	case "NOTPAY", "USERPAYING":
	default:
		return nil, errors.New("unsupported trade state")
	}
	transactionID := ""
	if t.TransactionId != nil {
		transactionID = *t.TransactionId
	}
	if state == "paid" && transactionID == "" {
		return nil, errors.New("missing transaction id")
	}
	return &Fact{OrderID: *t.OutTradeNo, TransactionID: transactionID, Amount: *t.Amount.Total,
		Currency: *t.Amount.Currency, MerchantID: *t.Mchid, AppID: *t.Appid, Status: state}, nil
}
