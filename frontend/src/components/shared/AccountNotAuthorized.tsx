import { LogOut, ShieldAlert } from "lucide-react";

/**
 * What a teacher sees when the backend answers 403: the token is valid and the
 * account behind it is not a teacher on this dashboard.
 *
 * THIS SCREEN EXISTS BECAUSE THE ALTERNATIVE TRAPPED PEOPLE. Before it, a 403
 * rendered as "Check your connection and try again" on every screen -- advice
 * that cannot work -- and on Profile it replaced the page's only Log out
 * button, so the one account that needed to sign out was the one account that
 * could not. Clearing browser storage by hand was the only way back.
 *
 * It names the signed-in email because that is almost always the whole answer:
 * the wrong account was used, or a learner account was. The email comes from
 * the Supabase session, not from an API call that would itself be refused.
 *
 * It does NOT offer a retry. The backend has decided who this caller is; the
 * same request would be refused the same way. The only moves are to sign in as
 * someone else, or to have a teacher account set up -- and this backend never
 * creates one, by design (that belongs to the student app).
 */
export interface AccountNotAuthorizedProps {
  /** The signed-in address, or null if the session has no email on it. */
  email: string | null;
  onSignOut: () => void;
}

export function AccountNotAuthorized({ email, onSignOut }: AccountNotAuthorizedProps) {
  return (
    <div className="mx-auto flex min-h-screen max-w-[480px] flex-col justify-center gap-6 p-4">
      <div className="flex flex-col items-center gap-3 text-center">
        <span className="flex h-16 w-16 items-center justify-center rounded-full bg-danger-soft">
          <ShieldAlert aria-hidden="true" size={32} className="text-danger-text" />
        </span>
        <h1 className="text-subtitle font-extrabold text-ink-primary">
          This account can&rsquo;t open the dashboard
        </h1>
      </div>

      <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface1 p-4 text-sm text-ink-secondary">
        {/* Never "your account is wrong" -- it may well be the right person and
            the wrong address, and they cannot tell which without being told
            WHICH address they are signed in as. */}
        <p>
          You are signed in as{" "}
          <span className="font-bold text-ink-primary">{email ?? "an unknown account"}</span>, and
          that account is not set up as a teacher here.
        </p>
        <p>
          Teacher accounts are created in the student app, not on this dashboard. Log out and sign
          in with your teacher account, or ask whoever set up your school&rsquo;s app to add one.
        </p>
      </div>

      <button
        type="button"
        onClick={onSignOut}
        className="flex min-h-[44px] w-full items-center justify-center gap-2 rounded-lg border border-danger bg-danger-soft px-4 text-sm font-bold text-danger-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
      >
        <LogOut aria-hidden="true" size={20} />
        Log out
      </button>
    </div>
  );
}
