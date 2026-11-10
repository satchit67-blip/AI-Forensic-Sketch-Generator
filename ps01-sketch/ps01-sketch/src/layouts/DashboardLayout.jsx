import { Outlet } from 'react-router-dom';
import Background from '../components/Background';
import Sidebar from '../components/Sidebar';
import { useStudio } from '../lib/useStudio';

// Persistent shell: sidebar + background stay mounted while the active page swaps in the <Outlet />.
export default function DashboardLayout() {
  const studio = useStudio();
  return (
    <div className="relative min-h-screen">
      <Background />
      <Sidebar />
      <div className="relative z-10 lg:pl-60">
        <div className="mx-auto flex max-w-[1400px] flex-col gap-6 p-3 sm:p-6">
          <Outlet context={studio} />
        </div>
      </div>
    </div>
  );
}
