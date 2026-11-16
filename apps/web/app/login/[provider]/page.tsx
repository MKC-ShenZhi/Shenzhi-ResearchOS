import { OAuthVerifyPage } from "@/features/login/OAuthVerifyPage";
import { turnstileConfig } from "@/config/turnstile";

export default async function Page({
  params,
}: {
  params: Promise<{ provider: string }>;
}) {
  const { provider } = await params;
  return (
    <OAuthVerifyPage
      provider={provider}
      turnstileAction={turnstileConfig.expectedAction}
    />
  );
}
