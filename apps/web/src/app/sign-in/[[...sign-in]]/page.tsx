import { SignIn } from "@clerk/nextjs";

// Catch-all route ([[...sign-in]]) so Clerk's multi-step flows (MFA, SSO
// callbacks) resolve under the same path.
export default function SignInPage() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <SignIn />
    </div>
  );
}
