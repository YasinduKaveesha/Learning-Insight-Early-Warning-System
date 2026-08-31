import { Route, Routes } from "react-router-dom";
import ClassroomReportsRoute from "./routes/classroom-reports/ClassroomReportsRoute";
import ClassroomRequestsRoute from "./routes/classroom-requests/ClassroomRequestsRoute";
import ClassroomRoute from "./routes/classroom/ClassroomRoute";
import ClassroomWatchRoute from "./routes/classroom-watch/ClassroomWatchRoute";
import ClassesRoute from "./routes/classes/ClassesRoute";
import GalleryRoute from "./routes/gallery/GalleryRoute";
import HomeRoute from "./routes/home/HomeRoute";
import ProfileRoute from "./routes/profile/ProfileRoute";
import StudentRoute from "./routes/student/StudentRoute";
import StudentSessionsRoute from "./routes/student-sessions/StudentSessionsRoute";
import WatchRoute from "./routes/watch/WatchRoute";

function App() {
  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<HomeRoute />} />
          <Route path="/classes" element={<ClassesRoute />} />
          <Route path="/watch/:studentId?" element={<WatchRoute />} />
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
  );
}

export default App;
