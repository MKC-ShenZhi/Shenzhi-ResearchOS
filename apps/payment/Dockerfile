FROM golang:1.24-bookworm AS build
WORKDIR /src
COPY apps/payment/go.mod apps/payment/go.sum ./
RUN go mod download
COPY apps/payment/ ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /payment ./cmd/server

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /payment /payment
EXPOSE 8090
HEALTHCHECK --interval=10s --timeout=5s CMD ["/payment", "healthcheck"]
ENTRYPOINT ["/payment"]
