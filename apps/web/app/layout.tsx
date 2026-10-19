import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import Script from "next/script";
import { AuthProvider } from "@/components/auth/auth-provider";
import { FeatureAvailabilityProvider } from "@/components/common/feature-availability-provider";
import { ThemeStoreHydrator } from "@/components/common/theme-store-hydrator";
import { QueryProvider } from "@/providers/query-provider";
import { THEME_PRESETS, MODE_THEME_PRESETS, isDarkThemePreset } from "@/lib/theme-presets";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "深知 ShenZhi · Research OS",
  description: "深知 —— 面向科研工作者的论文发现、投稿跟踪与 AI 研究助手平台",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", interactiveWidget: "resizes-content" };

/**
 * 首屏前确定主题,避免闪烁:
 * ?theme=<视觉预设|dark|light|system>(调试/分享)> localStorage > 系统偏好
 */
const themeScript = `(function(){try{var q=new URLSearchParams(location.search).get("theme");var ps=${JSON.stringify(THEME_PRESETS.map((preset) => preset.id))};var ds=${JSON.stringify(THEME_PRESETS.filter((preset) => isDarkThemePreset(preset.id)).map((preset) => preset.id))};var ms=${JSON.stringify(MODE_THEME_PRESETS)};var qm=q==="dark"||q==="light"||q==="system";var p=qm?"shenzhi":ps.indexOf(q)>-1?q:localStorage.getItem("shenzhi-theme-preset");if(ps.indexOf(p)<0)p="shenzhi";var t=qm?q:localStorage.getItem("shenzhi-theme");if(t!=="dark"&&t!=="light"&&t!=="system")t="system";var c={appearance:"light"};try{var cs=JSON.parse(localStorage.getItem("shenzhi-theme-custom")||"{}");if(cs.appearance==="dark")c.appearance="dark"}catch(_e){}var m=window.matchMedia("(prefers-color-scheme: dark)").matches;var d=p==="custom"?c.appearance==="dark":ds.indexOf(p)>-1||(ms.indexOf(p)>-1&&(t==="dark"||(t==="system"&&m)));document.documentElement.dataset.theme=p;document.documentElement.classList.toggle("dark",d);if(p==="custom"){try{var vs=JSON.parse(localStorage.getItem("shenzhi-theme-custom-vars")||"{}");Object.keys(vs).forEach(function(k){if((k.indexOf("--color-")===0||k.indexOf("--shadow-")===0||k.indexOf("--page-")===0||k.indexOf("--surface-")===0)&&typeof vs[k]==="string"&&vs[k].indexOf("url(")<0)document.documentElement.style.setProperty(k,vs[k])})}catch(_v){}}}catch(e){}})()`;

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
