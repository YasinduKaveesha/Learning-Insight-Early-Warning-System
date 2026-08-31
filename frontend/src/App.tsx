import { Route, Routes } from "react-router-dom";
import { AppNav } from "./components/shared/AppNav";
import ClassroomReportsRoute from "./routes/classroom-reports/ClassroomReportsRoute";
import ClassroomRequestsRoute from "./routes/classroom-requests/ClassroomRequestsRoute";
import ClassroomRoute from "./routes/classroom/ClassroomRoute";
import ClassroomWatchRoute from "./routes/classroom-watch/ClassroomWatchRoute";
import ClassesRoute from "./routes/classes/ClassesRoute";
import HomeRoute from "./routes/home/HomeRoute";
import ProfileRoute from "./routes/profile/ProfileRoute";
import StudentRoute from "./routes/student/StudentRoute";
import StudentSessionsRoute from "./routes/student-sessions/StudentSessionsRoute";
import WatchRoute from "./routes/watch/WatchRoute";

function App() {
  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      <AppNav />
      <main className="flex-1 pb-[44px] lg:pb-0">
        <Routes>
          <Route path="/" element={<HomeRoute />} />
          <Route path="/classes" element={<ClassesRoute />} />
          <Route path="/watch" element={<WatchRoute />} />
          <Route path="/profile" element={<ProfileRoute />} />

          <Route path="/classes/:classId" element={<ClassroomRoute />} />
          <Route
            path="/classes/:classId/watch"
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
        </Routes>
      </main>
    </div>
  );
}

export default App;
