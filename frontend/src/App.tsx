import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import { AuthorizationBoundary } from "./auth/AuthorizationBoundary";
import { ForegroundPriority } from "./components/shared/ForegroundPriority";
import { RedirectIfAuthed, RequireAuth } from "./auth/RouteGuard";
import { SessionProvider } from "./auth/SessionProvider";
import LoginRoute from "./routes/login/LoginRoute";
import ClassroomReportsRoute from "./routes/classroom-reports/ClassroomReportsRoute";
import ClassroomRequestsRoute from "./routes/classroom-requests/ClassroomRequestsRoute";
import ClassroomRoute from "./routes/classroom/ClassroomRoute";
import ClassroomWatchRoute from "./routes/classroom-watch/ClassroomWatchRoute";
import CompdRoute from "./routes/compd/CompdRoute";
import CompdStudentRoute from "./routes/compd/CompdStudentRoute";
import GalleryRoute from "./routes/gallery/GalleryRoute";
import HomeRoute from "./routes/home/HomeRoute";
import ProfileRoute from "./routes/profile/ProfileRoute";
import StudentRoute from "./routes/student/StudentRoute";
import StudentSessionsRoute from "./routes/student-sessions/StudentSessionsRoute";
import WatchRoute from "./routes/watch/WatchRoute";

function App() {
  return (
    <SessionProvider>
      <div className="flex min-h-screen flex-col lg:flex-row">
        <main className="flex-1">
          <Routes>
            <Route
              path="/login"
              element={
                <RedirectIfAuthed>
                  <LoginRoute />
                </RedirectIfAuthed>
              }
            />

            {/* Everything below requires a session (frontend_plan §11.0). */}
            <Route
              element={
                <RequireAuth>
                  {/* Signed in is not the same as authorized. RequireAuth
                      answers the first; this answers the second, once, for
                      every protected screen. */}
                  <AuthorizationBoundary>
                    {/* Renders nothing. Holds the background warm-up while the
                        open screen loads, on every route and every reload. */}
                    <ForegroundPriority />
                    <Outlet />
                  </AuthorizationBoundary>
                </RequireAuth>
              }
            >
          <Route path="/" element={<HomeRoute />} />
          {/* The All Classes page was removed (2026-09-14): Home already lists
              every class. Kept as a redirect, not deleted outright, because a
              teacher's browser history may still hold /classes -- pressing
              Back must land somewhere real, not on a blank page. */}
          <Route path="/classes" element={<Navigate to="/" replace />} />
          <Route path="/watch/:studentId?" element={<WatchRoute />} />
          {/* compD's teacher side (owner decision D-028): one page with two
              tabs, and one page per student. */}
          <Route path="/compd" element={<CompdRoute />} />
          <Route path="/compd/students/:studentId" element={<CompdStudentRoute />} />
          <Route path="/profile" element={<ProfileRoute />} />

          <Route path="/classes/:classId" element={<ClassroomRoute />} />
          <Route
            path="/classes/:classId/watch/:studentId?"
            element={<ClassroomWatchRoute />}
          />
          <Route
            path="/classes/:classId/requests"
            element={<ClassroomRequestsRoute />}
          />
          <Route
            path="/classes/:classId/reports"
            element={<ClassroomReportsRoute />}
          />

          <Route path="/students/:studentId" element={<StudentRoute />} />
          <Route
            path="/students/:studentId/sessions"
            element={<StudentSessionsRoute />}
          />
            </Route>

            {/* Dev-only component gallery (Step 4 acceptance surface).
                Excluded from production: import.meta.env.DEV is statically
                false in a `vite build`, so this route (and its import) is
                dead-code-eliminated from the production bundle. */}
            {import.meta.env.DEV ? (
              <Route path="/__gallery" element={<GalleryRoute />} />
            ) : null}
          </Routes>
        </main>
      </div>
    </SessionProvider>
  );
}

export default App;
