import type { RouteObject } from "react-router-dom";
import Layout from "../components/feature/Layout";
import NotFound from "../pages/NotFound";
import Home from "../pages/home/page";
import Login from "../pages/login/page";
import Register from "../pages/register/page";
import Support from "../pages/support/page";
import Warranty from "../pages/warranty/page";
import Terms from "../pages/terms/page";
import AdminPanel from "../pages/adminkonvy/page";
import TransactionHistory from "../pages/transactions/page";
import MyAccounts from "../pages/my-accounts/page";

const routes: RouteObject[] = [
  {
    path: "/",
    element: <Layout />,
    children: [
      {
        path: "/",
        element: <Home />,
      },
      {
        path: "/login",
        element: <Login />,
      },
      {
        path: "/register",
        element: <Register />,
      },
      {
        path: "/support",
        element: <Support />,
      },
      {
        path: "/warranty",
        element: <Warranty />,
      },
      {
        path: "/terms",
        element: <Terms />,
      },
      {
        path: "/adminkonvy",
        element: <AdminPanel />,
      },
      {
        path: "/transactions",
        element: <TransactionHistory />,
      },
      {
        path: "/my-accounts",
        element: <MyAccounts />,
      },
      {
        path: "*",
        element: <NotFound />,
      },
    ],
  },
];

export default routes;