
import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import { supabase } from '../lib/supabase'

interface User {
  id: string
  username: string
  email: string
  role: 'customer' | 'owner'
  created_at: string
}

interface AuthContextType {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<{ success: boolean; error?: string }>
  register: (username: string, password: string) => Promise<{ success: boolean; error?: string }>
  adminLogin: (password: string) => Promise<{ success: boolean; error?: string }>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    checkUser()
    
    // Listen for auth changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange(async (event, session) => {
      if (event === 'SIGNED_IN' && session?.user) {
        await loadUserProfile(session.user.id)
      } else if (event === 'SIGNED_OUT') {
        setUser(null)
      }
    })

    return () => subscription.unsubscribe()
  }, [])

  const checkUser = async () => {
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (session?.user) {
        await loadUserProfile(session.user.id)
      }
    } catch (error) {
      console.error('Error checking user:', error)
    } finally {
      setLoading(false)
    }
  }

  const loadUserProfile = async (userId: string) => {
    try {
      const { data: profile, error } = await supabase
        .from('user_profiles')
        .select('*')
        .eq('id', userId)
        .single()

      if (error) {
        console.error('Error loading profile:', error)
        return
      }

      if (profile) {
        setUser({
          id: profile.id,
          username: profile.username,
          email: profile.email,
          role: profile.role,
          created_at: profile.created_at
        })
      }
    } catch (error) {
      console.error('Error loading user profile:', error)
    }
  }

  const register = async (username: string, password: string) => {
    try {
      // Check if username already exists
      const { data: existingProfile } = await supabase
        .from('user_profiles')
        .select('username')
        .eq('username', username)
        .single()

      if (existingProfile) {
        return { success: false, error: 'Username already exists' }
      }

      // Create unique email for Supabase auth
      const uniqueEmail = `${username}_${Date.now()}@local.app`

      // Sign up with Supabase auth
      const { data: authData, error: authError } = await supabase.auth.signUp({
        email: uniqueEmail,
        password: password,
        options: {
          data: { username: username }
        }
      })

      if (authError) {
        console.error('Auth error:', authError)
        return { success: false, error: 'Registration failed' }
      }

      if (authData.user) {
        // Create user profile in database
        const { error: profileError } = await supabase
          .from('user_profiles')
          .insert([{
            id: authData.user.id,
            username: username,
            email: uniqueEmail,
            role: 'customer'
          }])

        if (profileError) {
          console.error('Profile creation error:', profileError)
          return { success: false, error: 'Failed to create user profile' }
        }

        // Track registration in Google Forms
        try {
          const formData = new FormData()
          formData.append('username', username)
          formData.append('user_id', authData.user.id)
          formData.append('email', uniqueEmail)
          formData.append('role', 'customer')
          formData.append('registration_date', new Date().toISOString())
          formData.append('status', 'registered')

          await fetch('https://readdy.ai/api/form/i9xtl9tqr7oeun7bsm80', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: new URLSearchParams(formData as any).toString()
          })
        } catch (formError) {
          console.error('Error tracking registration:', formError)
          // Don't fail registration if form submission fails
        }

        // Load the user profile
        await loadUserProfile(authData.user.id)
        return { success: true }
      }

      return { success: false, error: 'Registration failed' }
    } catch (error) {
      console.error('Registration error:', error)
      return { success: false, error: 'Registration failed' }
    }
  }

  const login = async (username: string, password: string) => {
    try {
      // Get user profile to find email
      const { data: profile, error: profileError } = await supabase
        .from('user_profiles')
        .select('*')
        .eq('username', username)
        .single()
      
      if (profileError || !profile) {
        return { success: false, error: 'Invalid username or password' }
      }

      // Sign in with email and password
      const { data, error } = await supabase.auth.signInWithPassword({
        email: profile.email,
        password: password,
      })

      if (error) {
        console.error('Login error:', error)
        return { success: false, error: 'Invalid username or password' }
      }

      if (data.user) {
        await loadUserProfile(data.user.id)
        return { success: true }
      }

      return { success: false, error: 'Login failed' }
    } catch (error) {
      console.error('Login error:', error)
      return { success: false, error: 'Login failed' }
    }
  }

  const adminLogin = async (password: string) => {
    try {
      if (password !== 'konvy123') {
        return { success: false, error: 'Invalid admin password' }
      }

      // Sign in as admin with special admin credentials
      const { data, error } = await supabase.auth.signInWithPassword({
        email: 'admin@konvy.local',
        password: password,
      })

      if (error) {
        // If admin account doesn't exist, create it
        const { data: signupData, error: signupError } = await supabase.auth.signUp({
          email: 'admin@konvy.local',
          password: password,
        })

        if (signupError) {
          console.error('Admin signup error:', signupError)
          return { success: false, error: 'Admin login failed' }
        }

        if (signupData.user) {
          // Create admin profile
          await supabase
            .from('user_profiles')
            .insert([{
              id: signupData.user.id,
              username: 'Konvy',
              email: 'admin@konvy.local',
              role: 'owner'
            }])

          await loadUserProfile(signupData.user.id)
          return { success: true }
        }
      } else if (data.user) {
        await loadUserProfile(data.user.id)
        return { success: true }
      }

      return { success: false, error: 'Admin login failed' }
    } catch (error) {
      console.error('Admin login error:', error)
      return { success: false, error: 'Admin login failed' }
    }
  }

  const logout = async () => {
    try {
      await supabase.auth.signOut()
      setUser(null)
    } catch (error) {
      console.error('Error during logout:', error)
      setUser(null)
    }
  }

  return (
    <AuthContext.Provider value={{
      user,
      loading,
      login,
      register,
      adminLogin,
      logout
    }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
