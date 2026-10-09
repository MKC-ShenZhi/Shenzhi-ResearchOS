import type { Metadata } from "next";
import type { ReactNode } from "react";
import Script from "next/script";
import { AuthProvider } from "@/components/auth/auth-provider";
import { FeatureAvailabilityProvider } from "@/components/common/feature-availability-provider";
import { ThemeStoreHydrator } from "@/components/common/theme-store-hydrator";
import { QueryProvider } from "@/providers/query-provider";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "深知 ShenZhi · Research OS",
  description: "深知 —— 面向科研工作者的论文发现、投稿跟踪与 AI 研究助手平台",
};

/**
 * 首屏前确定主题,避免闪烁:
 * ?theme=<视觉预设|dark|light|system>(调试/分享)> localStorage > 系统偏好
 */
const themeScript = `(function(){try{var q=new URLSearchParams(location.search).get("theme");var ps=["shenzhi","gpt","claude","alphaxiv","apple-light","apple-dark"];var qm=q==="dark"||q==="light"||q==="system";var p=qm?"shenzhi":ps.indexOf(q)>-1?q:localStorage.getItem("shenzhi-theme-preset");if(ps.indexOf(p)<0)p="shenzhi";var t=qm?q:localStorage.getItem("shenzhi-theme");if(t!=="dark"&&t!=="light"&&t!=="system")t="system";var m=window.matchMedia("(prefers-color-scheme: dark)").matches;var d=p==="apple-dark"||(p==="shenzhi"&&(t==="dark"||(t==="system"&&m)));document.documentElement.dataset.theme=p;document.documentElement.classList.toggle("dark",d)}catch(e){}})()`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN" data-theme="shenzhi" suppressHydrationWarning>
      <body suppressHydrationWarning>
        <Script id="shenzhi-theme" strategy="beforeInteractive">
          {themeScript}
        </Script>
        <FeatureAvailabilityProvider>
          <AuthProvider>
            <ThemeStoreHydrator />
            <QueryProvider>{children}</QueryProvider>
          </AuthProvider>
        </FeatureAvailabilityProvider>
      </body>
    </html>
  );
}
