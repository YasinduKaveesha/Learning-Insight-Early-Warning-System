import { useParams } from "react-router-dom";
import { WatchListScreen } from "../watch/WatchListScreen";

export default function ClassroomWatchRoute() {
  const { classId, studentId } = useParams<{ classId: string; studentId?: string }>();
  return <WatchListScreen classId={classId} selectedStudentId={studentId} />;
}
