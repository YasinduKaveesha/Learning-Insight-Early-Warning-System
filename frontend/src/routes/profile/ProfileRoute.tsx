import { useQuery, useQueryClient } from "@tanstack/react-query";
import { GraduationCap, House, LogOut, Mail, User, Users } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { client } from "../../api/client";
import { useSession } from "../../auth/SessionProvider";
import { ErrorState } from "../../components/shared/ErrorState";
import { ProfileSkeleton } from "../../components/skeletons/PageSkeletons";

/**
 * Profile (plan §3). The teacher's own details and a way out, in the shape the
 * student app's profile uses — avatar, a card of labelled rows, a log-out
 * button set apart — in this dashboard's palette.
 *
 * EVERY ROW IS A VALUE THE SYSTEM ALREADY HOLDS: the name from
 * `teacher_profiles`, the email from the signed-in Supabase session, and the
 * class and student counts from `/home`. Nothing here is a setting, a
 * preference or account management: those were never asked for, and inventing
 * them would mean inventing what they do.
 *
 * Sign-out clears the Supabase session AND the TanStack Query cache. Clearing
 * the cache is not optional — one teacher's cohort must never survive into
 * another teacher's session (frontend_plan §11.0) — then lands on /login.
 */
export default function ProfileRoute() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { signOut, session } = useSession();

  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["home"],
    queryFn: () => client.getHome(),
  });

  async function handleSignOut() {
    await signOut();
    // Order matters less than completeness: the cache must be empty before
    // the next teacher's data can load.
    queryClient.clear();
    navigate("/login", { replace: true });
  }

  // Supabase holds the email; the dashboard never stores a copy of it.
  const email = session?.user?.email ?? null;

  return (
    // Full height, two parts: the profile, centred in all the space there is,
    // and the Home button at the foot. No bar -- the button sits on the page.
    <div className="mx-auto flex min-h-screen max-w-[480px] lg:max-w-[720px] flex-col p-4">
      {/* The visible "Profile" title was removed at explicit direction -- the
          avatar and name already say whose page this is. It stays for screen
          readers so the page still has a heading to land on (the hardening
          pass's "sane heading hierarchy"). */}
      <h1 className="sr-only">Profile</h1>

      <div className="flex flex-1 flex-col justify-center gap-6">
      {isPending ? (
        <ProfileSkeleton />
      ) : isError ? (
        <ErrorState
          message="Couldn't load your profile. Check your connection and try again."
          onRetry={() => refetch()}
        />
      ) : (
        <>
          <div className="flex flex-col items-center gap-2">
            <div className="flex h-24 w-24 items-center justify-center rounded-full border-4 border-surface1 bg-primary shadow-sm">
              <User aria-hidden="true" size={44} className="text-primary-foreground" />
            </div>
            <p className="text-subtitle font-extrabold text-ink-primary">{data.teacherName}</p>
          </div>

          <dl className="flex flex-col rounded-lg border border-border bg-surface1 p-3">
            <ProfileRow
              icon={<User aria-hidden="true" size={20} className="text-primary-foreground" />}
              tint="bg-accent-blue"
              label="Name"
              value={data.teacherName}
            />
            <ProfileRow
              icon={<Mail aria-hidden="true" size={20} className="text-primary-foreground" />}
              tint="bg-accent-green"
              label="Email"
              // Null only if the session went away mid-render; say so rather
              // than printing an empty row that looks like a missing value.
              value={email ?? "Not available"}
            />
            <ProfileRow
              icon={<GraduationCap aria-hidden="true" size={20} className="text-primary-foreground" />}
              tint="bg-primary"
              label="Classes"
              value={String(data.classCount)}
            />
            <ProfileRow
              icon={<Users aria-hidden="true" size={20} className="text-primary-foreground" />}
              tint="bg-accent-blue"
              label="Students"
              value={String(data.activeStudents)}
              isLast
            />
          </dl>

          {/* Set apart from the rows above, and in the danger tint the student
              app uses for the same control -- this is the one action on the
              screen that ends the session. */}
          <button
            type="button"
            onClick={() => void handleSignOut()}
            className="flex min-h-[44px] w-full items-center justify-center gap-2 rounded-lg border border-danger bg-danger-soft px-4 text-sm font-bold text-danger-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
          >
            <LogOut aria-hidden="true" size={20} />
            Log out
          </button>
        </>
      )}
      </div>

      {/* The page's way home. It has no header, so this is it -- the SAME House
          icon in the SAME bordered circle every other screen's header uses,
          only larger, so a teacher recognises it. It sits on the page rather
          than in a bar (the white bar was removed at explicit direction), and
          in the normal flow, so it can never cover the Log out button. */}
      <nav aria-label="Profile navigation" className="flex justify-center pt-6">
        <div className="flex justify-center">
          <Link
            to="/"
            aria-label="Home"
            className="flex h-14 w-14 items-center justify-center rounded-full border border-border-strong bg-surface1 text-ink-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
          >
            <House aria-hidden="true" size={28} />
          </Link>
        </div>
      </nav>
    </div>
  );
}

function ProfileRow({
  icon,
  tint,
  label,
  value,
  isLast = false,
}: {
  icon: React.ReactNode;
  tint: string;
  label: string;
  value: string;
  isLast?: boolean;
}) {
  return (
    <div
      className={`flex items-center gap-3 py-3 ${isLast ? "" : "border-b border-border"}`}
    >
      <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${tint}`}>
        {icon}
      </span>
      <div className="flex min-w-0 flex-col">
        <dt className="text-sm text-ink-secondary">{label}</dt>
        {/* `break-all` so a long email wraps inside the card at 375px rather
            than pushing the row wider than the screen. */}
        <dd className="break-all text-base font-semibold text-ink-primary">{value}</dd>
      </div>
    </div>
  );
}
