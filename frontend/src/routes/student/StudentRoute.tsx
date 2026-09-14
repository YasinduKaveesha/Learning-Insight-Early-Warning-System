import { useParams } from "react-router-dom";
import { StudentDetail } from "../../components/student/StudentDetail";

/** Thin route wrapper — the actual screen is StudentDetail, shared with the
 * ≥1024px watch-list master-detail pane (hardening-pass gap 2). */
export default function StudentRoute() {
  const { studentId } = useParams<{ studentId: string }>();
  return <StudentDetail studentId={studentId} />;
}
