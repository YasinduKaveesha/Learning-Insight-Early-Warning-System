import { useParams } from "react-router-dom";
import { WatchListScreen } from "../watch/WatchListScreen";

export default function ClassroomWatchRoute() {
  const { classId } = useParams<{ classId: string }>();
  return <WatchListScreen classId={classId} />;
}
