// Route guard (frontend_plan §11.0):
//   unauthenticated            -> /login
//   authenticated while /login -> home
// While the first getSession() is resolving, render a skeleton rather than
// flashing the login screen at an already-signed-in teacher.

import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { LoadingSkeleton } from "../components/shared/LoadingSkeleton";
import { useSession } from "./SessionProvider";

function FullPageLoading() {
  return (
    <div className="mx-auto flex max-w-[480px] flex-col gap-4 p-4">
      <LoadingSkeleton rows={1} rowHeight={44} />
      <LoadingSkeleton rows={3} rowHeight={64} />
    </div>
  );
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { status, isAuthed } = useSession();
  const location = useLocation();

  if (status === "loading") return <FullPageLoading />;
  if (!isAuthed) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}

export function RedirectIfAuthed({ children }: { children: ReactNode }) {
  const { status, isAuthed } = useSession();

  if (status === "loading") return <FullPageLoading />;
  if (isAuthed) return <Navigate to="/" replace />;
  return <>{children}</>;
}
