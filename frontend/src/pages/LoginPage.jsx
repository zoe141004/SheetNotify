import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../lib/api';
import toast from 'react-hot-toast';
import { FiLogOut } from 'react-icons/fi';
// Import Google Icon
import { FcGoogle } from 'react-icons/fc';

export default function LoginPage() {
  const { user } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (user) {
      navigate('/');
    }
  }, [user, navigate]);

  const handleGoogleLogin = async () => {
    try {
      const { data } = await api.get('/auth/google/login');
      window.location.href = data.authorization_url;
    } catch (error) {
      toast.error('Failed to initiate login. Please check connection.');
    }
  };

  return (
    <div className="min-h-screen bg-dark-900 flex items-center justify-center p-4 relative overflow-hidden">
      {/* Background decoration */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-primary-600/10 rounded-full blur-[100px]" />
      
      <div className="glass-card max-w-md w-full p-8 relative z-10 animate-fade-in">
        <div className="text-center mb-8">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary-500 to-accent-400 flex items-center justify-center text-white font-bold text-3xl mx-auto mb-6 shadow-lg shadow-primary-500/20">
            S
          </div>
          <h1 className="text-2xl font-bold mb-2">Welcome to SheetNotify</h1>
          <p className="text-gray-400">Get Telegram alerts for Google Sheets effortlessly.</p>
        </div>

        <div className="space-y-4">
          <button
            onClick={handleGoogleLogin}
            className="w-full flex items-center justify-center gap-3 bg-white text-gray-900 font-semibold px-6 py-3 rounded-xl hover:bg-gray-100 transition-colors shadow-lg active:scale-[0.98]"
          >
            <FcGoogle className="w-6 h-6" />
            Continue with Google
          </button>
          
          <p className="text-center text-xs text-gray-500 mt-6 px-4">
            By signing in, you agree to our Terms of Service and Privacy Policy.
          </p>
        </div>
      </div>
    </div>
  );
}
