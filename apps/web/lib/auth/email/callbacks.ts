import type { User } from "better-auth";

import {
  requireAuthEmailProvider,
  type AuthEmailProvider,
} from "../providers/email";

import {
  buildEmailOtpMessage,
  buildPasswordResetEmailMessage,
  buildVerificationEmailMessage,
  type EmailOtpType,
} from "./messages";

export interface BetterAuthEmailLinkCallbackData {
  user: User;
  url: string;
  token: string;
  newEmail?: string;
}

export interface BetterAuthEmailOtpCallbackData {
  email: string;
  otp: string;
  type: EmailOtpType;
}

export function createBetterAuthEmailCallbacks(
  provider: AuthEmailProvider | undefined,
) {
  return {
    sendVerificationEmail: async (
      data: BetterAuthEmailLinkCallbackData,
      _request?: Request,
    ) => {
      void _request;
      await requireAuthEmailProvider(provider).send(
        buildVerificationEmailMessage({
          user: data.user,
          url: data.url,
          newEmail: data.newEmail,
        }),
      );
    },
    sendResetPassword: async (
      data: BetterAuthEmailLinkCallbackData,
      _request?: Request,
    ) => {
      void _request;
      await requireAuthEmailProvider(provider).send(
        buildPasswordResetEmailMessage({ user: data.user, url: data.url }),
      );
    },
    sendVerificationOTP: async (
      data: BetterAuthEmailOtpCallbackData,
      _context?: unknown,
    ) => {
      void _context;
      await requireAuthEmailProvider(provider).send(buildEmailOtpMessage(data));
    },
  };
}
