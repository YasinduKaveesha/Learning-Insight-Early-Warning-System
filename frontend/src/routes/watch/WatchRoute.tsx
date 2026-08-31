import { useParams } from "react-router-dom";
import { WatchListScreen } from "./WatchListScreen";

export default function WatchRoute() {
  const { studentId } = useParams<{ studentId?: string }>();
  return <WatchListScreen selectedStudentId={studentId} />;
}
